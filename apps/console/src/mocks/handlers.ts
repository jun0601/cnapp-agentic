// MSW 핸들러 — API를 가로채 contracts/mock-*.json을 서빙(§15.2·§15.4).
// 백엔드 0으로 전 화면 동작. 실 API 나오면 browser.ts에서 MSW만 끄면 됨(스왑 포인트).
import { http, HttpResponse } from 'msw'
import findingsMock from '@contracts/mock-findings.json'
import pathsMock from '@contracts/mock-attack-paths.json'
import casesMock from '@contracts/mock-cases.json'
import type { Finding, AttackPath, Case, FindingDetail, FindingExplanation } from '@/api/types'
import { AUDIT_EVENTS, COMPLIANCE_REPORT } from './view-fixtures'

const BASE = import.meta.env.VITE_API_BASE ?? '/api'

const FINDINGS = findingsMock.findings as Finding[]
const PATHS = pathsMock.attack_paths as AttackPath[]
const CASES = casesMock.cases as Case[]

// finding_id를 finding_ids[]에 포함하는 case 조인(§15.4 — Evidence 탭 소스, UC0).
function caseForFinding(findingId: string): Case | null {
  return (
    CASES.find((c) => 'finding_ids' in c.finding && c.finding.finding_ids.includes(findingId)) ?? null
  )
}

// UC1 finding당 AI 설명. 엔진 미구현 → 파생/placeholder. ai_status≠done이면 본문 비움(UI가 placeholder).
function explanationFor(f: Finding): FindingExplanation {
  const c = caseForFinding(f.finding_id)
  if (f.ai_status !== 'done') {
    return { finding_id: f.finding_id, summary: '', why: '', how: '', ai_status: f.ai_status, case_id: c?.case_id ?? null }
  }
  return {
    finding_id: f.finding_id,
    summary: `${f.title} — control ${f.control_id} 위반(${f.pillar}).`,
    why: c?.reasoning?.narrative ?? `${f.resource_id} 리소스에서 ${f.control_id} 통제가 충족되지 않아 위험이 발생한다.`,
    how: '조치 카탈로그(§14) 참조 — 승인 경로(HITL)로만 적용.',
    ai_status: 'done',
    case_id: c?.case_id ?? null,
  }
}

const SEV_SORT = (a: Finding, b: Finding) => a.severity_id - b.severity_id
const PRIO_SORT = (a: Finding, b: Finding) => (b.priority_score ?? -1) - (a.priority_score ?? -1)

export const handlers = [
  // GET /findings?cloud&pillar&status&sort — 목록(UC2)
  http.get(`${BASE}/findings`, ({ request }) => {
    const url = new URL(request.url)
    const cloud = url.searchParams.get('cloud')
    const pillar = url.searchParams.get('pillar')
    const status = url.searchParams.get('status')
    const sort = url.searchParams.get('sort') ?? 'priority'

    let rows = FINDINGS.slice()
    if (cloud) rows = rows.filter((f) => f.cloud === cloud)
    if (pillar) rows = rows.filter((f) => f.pillar === pillar)
    if (status) rows = rows.filter((f) => f.status === status)
    rows.sort(sort === 'severity' ? SEV_SORT : PRIO_SORT)
    return HttpResponse.json(rows)
  }),

  // GET /findings/:id — 상세(UC0·UC1): finding + explanation + case 조인
  http.get(`${BASE}/findings/:id`, ({ params }) => {
    const f = FINDINGS.find((x) => x.finding_id === params.id)
    if (!f) return new HttpResponse(null, { status: 404 })
    const detail: FindingDetail = {
      finding: f,
      explanation: explanationFor(f),
      case: caseForFinding(f.finding_id),
    }
    return HttpResponse.json(detail)
  }),

  // GET /attack-paths — 대시보드 배너(요약 대신 전체 반환, 콘솔이 요약)
  http.get(`${BASE}/attack-paths`, () => HttpResponse.json(PATHS)),

  // GET /attack-paths/:id — attack-path 화면(UC3)
  http.get(`${BASE}/attack-paths/:id`, ({ params }) => {
    const p = PATHS.find((x) => x.attack_path_id === params.id)
    return p ? HttpResponse.json(p) : new HttpResponse(null, { status: 404 })
  }),

  // GET /scores — 대시보드 홈(목업 상수, §15.2)
  http.get(`${BASE}/scores`, () =>
    HttpResponse.json({
      aws: { secure_score: 62, label: 'AWS Security Hub' },
      azure: { secure_score: 74, label: 'Azure Defender / Entra' },
    }),
  ),

  // POST /remediations/:id/{approve,reject} — 조치(UC4) → SFn StartExecution만(목업 200)
  http.post(`${BASE}/remediations/:id/:action`, ({ params }) =>
    HttpResponse.json({ ok: true, id: params.id, action: params.action }),
  ),

  // POST /findings/:id/reanalyze (선택) — Orchestrator 재트리거(목업 202)
  http.post(`${BASE}/findings/:id/reanalyze`, () => new HttpResponse(null, { status: 202 })),

  // GET /system — AI·시스템 관측(목업 상수, 실값은 console-backend가 RDS·CloudWatch 집계)
  http.get(`${BASE}/system`, () =>
    HttpResponse.json({
      live: false,
      models: {
        chat: 'global.anthropic.claude-haiku-4-5-20251001-v1:0',
        embed: 'amazon.titan-embed-text-v2:0',
        engine: 'global.anthropic.claude-haiku-4-5-20251001-v1:0',
      },
      rag: { chunks: 24, controls: 14, dim: 1024, index: 'HNSW (cosine)' },
      bedrock: { invocations24h: 6, inputTokens24h: 7415, outputTokens24h: 1180 },
      data: { findingsOpen: 18, findingsTotal: 20, attackPaths: 1, cases: 1 },
    }),
  ),

  // GET /audit — 감사로그 뷰어(목업)
  http.get(`${BASE}/audit`, () => HttpResponse.json(AUDIT_EVENTS)),

  // GET /compliance — 컴플라이언스 리포트(UC5 목업)
  http.get(`${BASE}/compliance`, () => HttpResponse.json(COMPLIANCE_REPORT)),

  // POST /chat — 자연어 질의(목업 에코)
  http.post(`${BASE}/chat`, async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { q?: string }
    return HttpResponse.json({ answer: `(목업) "${body.q ?? ''}"에 대한 RAG 응답 자리` })
  }),
]
