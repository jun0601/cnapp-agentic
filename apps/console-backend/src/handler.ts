// 관제 콘솔 백엔드 — ALB → Lambda (console-app-design §4·§15.2).
// 프론트(apps/console)가 기대하는 API 표면을 그대로 제공(MSW handlers.ts의 서버판).
// 실 전환: 프론트 VITE_USE_MOCK=false + VITE_API_BASE=ALB URL → 이 Lambda가 응답(프론트 무변).
// 전부 read-only(쓰기는 Step Functions로만, §10) — POST 조치는 승인(approver)만 트리거.
import * as data from './data'
import { roleFromHeaders } from './auth'

// ── ALB Lambda 이벤트/응답(최소 타입, @types/aws-lambda 의존 회피) ──
interface AlbEvent {
  httpMethod: string
  path: string
  queryStringParameters?: Record<string, string> | null
  headers?: Record<string, string | undefined>
  body?: string | null
}
interface AlbResult {
  statusCode: number
  statusDescription?: string
  isBase64Encoded: boolean
  headers: Record<string, string>
  body: string
}

const json = (statusCode: number, body: unknown): AlbResult => ({
  statusCode,
  statusDescription: `${statusCode}`,
  isBase64Encoded: false,
  headers: { 'Content-Type': 'application/json; charset=utf-8' },
  body: JSON.stringify(body),
})

export async function handler(event: AlbEvent): Promise<AlbResult> {
  const method = (event.httpMethod || 'GET').toUpperCase()
  // ALB 리스너가 /api/* 로 라우팅하면 접두 제거(프론트 API_BASE 기본 /api)
  const path = (event.path || '/').replace(/^\/api(?=\/|$)/, '') || '/'
  const q = event.queryStringParameters ?? {}

  try {
    // ── GET ──
    if (method === 'GET') {
      if (path === '/findings') {
        return json(200, data.getFindings({ cloud: q.cloud, pillar: q.pillar, status: q.status, sort: q.sort }))
      }
      const fDetail = path.match(/^\/findings\/([^/]+)$/)
      if (fDetail) {
        const d = data.getFindingDetail(decodeURIComponent(fDetail[1]))
        return d ? json(200, d) : json(404, { error: 'finding not found' })
      }
      if (path === '/attack-paths') return json(200, data.getAttackPaths())
      const pDetail = path.match(/^\/attack-paths\/([^/]+)$/)
      if (pDetail) {
        const p = data.getAttackPath(decodeURIComponent(pDetail[1]))
        return p ? json(200, p) : json(404, { error: 'attack-path not found' })
      }
      if (path === '/scores') return json(200, data.getScores())
      if (path === '/audit') return json(200, data.getAudit())
      if (path === '/compliance') return json(200, data.getCompliance())
    }

    // ── POST ──
    if (method === 'POST') {
      const rem = path.match(/^\/remediations\/([^/]+)\/(approve|reject)$/)
      if (rem) {
        // 조치 승인/반려는 approver만(HITL, §7·§17). 콘솔은 SFn StartExecution만 트리거.
        if (roleFromHeaders(event.headers) !== 'approver') {
          return json(403, { error: 'approver 권한 필요(조치 승인은 보안관리자만)' })
        }
        // 실 전환: Step Functions StartExecution(승인 시). 지금은 트리거 확인만.
        return json(200, { ok: true, id: rem[1], action: rem[2] })
      }
      if (path.match(/^\/findings\/[^/]+\/reanalyze$/)) {
        // 재분석: Orchestrator 재트리거(선택 기능). 지금은 accepted만.
        return json(202, { accepted: true })
      }
      if (path === '/chat') {
        const body = safeJson(event.body) as { q?: string }
        // 실 전환: Bedrock RAG 응답. 지금은 에코 placeholder.
        return json(200, { answer: `(mock) "${body.q ?? ''}"에 대한 RAG 응답 자리` })
      }
    }

    return json(404, { error: `no route: ${method} ${path}` })
  } catch (e) {
    return json(500, { error: e instanceof Error ? e.message : 'internal error' })
  }
}

function safeJson(body: string | null | undefined): unknown {
  if (!body) return {}
  try {
    return JSON.parse(body)
  } catch {
    return {}
  }
}
