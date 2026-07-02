// 데이터 계층 — mock(계약 JSON 읽기) / real(pgvector) 추상화.
// 콘솔 프론트가 기대하는 응답을 만든다(apps/console/src/mocks/handlers.ts의 서버판).
// 실 전환: USE_MOCK=false + PG_DSN → pgvector 쿼리(아래 real 경로). 핸들러 로직은 무변.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

// ── 계약 타입(필요 필드만) — SSOT는 contracts/*.schema.json ──
export interface Finding {
  finding_id: string
  cloud: string
  resource_id: string
  resource_type: string
  pillar: string
  control_id: string
  title: string
  severity_id: number
  status: string
  priority_score: number | null
  attack_path_id: string | null
  ai_status: string
}
export interface AttackPath {
  attack_path_id: string
  severity_id: number
  nodes: unknown[]
  edges: unknown[]
  narrative_text: string
}
export interface Case {
  case_id: string
  finding: { finding_ids?: string[] }
  reasoning?: { narrative?: string }
  evidence?: unknown[]
}
export interface FindingExplanation {
  finding_id: string
  summary: string
  why: string
  how: string
  ai_status: string
  case_id: string | null
}
export interface FindingDetail {
  finding: Finding
  explanation: FindingExplanation
  case: Case | null
}

const USE_MOCK = (process.env.USE_MOCK ?? 'true') !== 'false'
// Lambda 번들 시 contracts를 함께 패키징하거나 CONTRACTS_DIR로 지정. 로컬 mock은 레포 contracts.
const CONTRACTS_DIR = process.env.CONTRACTS_DIR ?? join(__dirname, '..', '..', '..', 'contracts')

function loadJson<T>(name: string): T {
  return JSON.parse(readFileSync(join(CONTRACTS_DIR, name), 'utf-8')) as T
}

// ── mock 소스(계약 골든) — lazy 캐시 ──
let _findings: Finding[] | null = null
let _paths: AttackPath[] | null = null
let _cases: Case[] | null = null
function mockFindings(): Finding[] {
  return (_findings ??= loadJson<{ findings: Finding[] }>('mock-findings.json').findings)
}
function mockPaths(): AttackPath[] {
  return (_paths ??= loadJson<{ attack_paths: AttackPath[] }>('mock-attack-paths.json').attack_paths)
}
function mockCases(): Case[] {
  return (_cases ??= loadJson<{ cases: Case[] }>('mock-cases.json').cases)
}

// ── 조인·파생(handlers.ts와 동일 규칙) ──
function caseForFinding(findingId: string, cases: Case[]): Case | null {
  return cases.find((c) => c.finding.finding_ids?.includes(findingId)) ?? null
}
function explanationFor(f: Finding, cases: Case[]): FindingExplanation {
  const c = caseForFinding(f.finding_id, cases)
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

export interface FindingsFilter {
  cloud?: string
  pillar?: string
  status?: string
  sort?: string
}

// ── 공개 API(핸들러가 호출) ──
export function getFindings(filter: FindingsFilter): Finding[] {
  if (!USE_MOCK) return pgFindings(filter)
  let rows = mockFindings().slice()
  if (filter.cloud) rows = rows.filter((f) => f.cloud === filter.cloud)
  if (filter.pillar) rows = rows.filter((f) => f.pillar === filter.pillar)
  if (filter.status) rows = rows.filter((f) => f.status === filter.status)
  rows.sort(filter.sort === 'severity' ? SEV_SORT : PRIO_SORT)
  return rows
}

export function getFindingDetail(id: string): FindingDetail | null {
  if (!USE_MOCK) return pgFindingDetail(id)
  const f = mockFindings().find((x) => x.finding_id === id)
  if (!f) return null
  const cases = mockCases()
  return { finding: f, explanation: explanationFor(f, cases), case: caseForFinding(id, cases) }
}

export function getAttackPaths(): AttackPath[] {
  return USE_MOCK ? mockPaths() : pgAttackPaths()
}
export function getAttackPath(id: string): AttackPath | null {
  if (!USE_MOCK) return pgAttackPath(id)
  return mockPaths().find((p) => p.attack_path_id === id) ?? null
}

// scores·audit·compliance는 MVP에선 상수/배치 산출(§15.2). 실 전환 시 scores/audit/compliance 조회.
export function getScores() {
  return {
    aws: { secure_score: 62, label: 'AWS Security Hub' },
    azure: { secure_score: 74, label: 'Azure Defender / Entra' },
  }
}

// ⚠️ 응답 shape는 프론트 계약(apps/console/src/api/view-types.ts)과 정확히 일치해야 함.
// (audit/compliance는 아직 contracts로 졸업 안 함 — 프론트 view-types가 사실상 SSOT. VITE_USE_MOCK=false 스왑 시 이 shape로 화면 렌더)
// AuditEvent = {id, ts, actor, role, action, target, result}
export function getAudit() {
  return [
    { id: 'a12', ts: '2026-06-30T02:15:40Z', actor: 'jh_lee@demo', role: 'approver', action: 'approve', target: 'aws:s3_bucket:member-pii-prod', result: 'S3 Public Access Block 적용 → SFn 실행 시작' },
    { id: 'a09', ts: '2026-06-30T02:05:11Z', actor: 'engine', role: 'system', action: 'verdict', target: 'case c0000000-…-0001', result: 'Reasoning confirmed (신뢰도 0.93) — 골든 경로 Critical 정당' },
    { id: 'a07', ts: '2026-06-30T02:03:10Z', actor: 'engine', role: 'system', action: 'verdict', target: 'aws:s3_bucket:member-pii-prod', result: 'Evidence: s3:GetBucketPolicy — 공개 버킷 확인' },
    { id: 'a05', ts: '2026-06-30T02:00:30Z', actor: 'scanner:macie', role: 'system', action: 'scan', target: 'aws:s3_bucket:member-pii-prod', result: 'SensitiveData:PII 탐지 → f…0007' },
    { id: 'a02', ts: '2026-06-30T01:58:40Z', actor: 'jh_lee@demo', role: 'approver', action: 'login', target: 'console', result: 'Entra SSO 로그인 (approver)' },
  ]
}
// ComplianceReport = {framework, generated_at, score, domains:[{code, name, controls:[{code, title, status, mapped_control?, findings}]}]}
export function getCompliance() {
  const domains = [
    { code: '2.5', name: '인증 및 권한관리', controls: [
      { code: '2.5.3', title: 'IAM/IRSA 최소권한', status: 'fail', mapped_control: 'INTERNAL-IAM-OVERPRIV-001', findings: 1 },
      { code: '2.5.6', title: 'Entra 앱 과도권한 금지', status: 'fail', mapped_control: 'INTERNAL-ENTRA-OVERPRIV-APP-001', findings: 1 },
    ] },
    { code: '2.6', name: '접근통제', controls: [
      { code: '2.6.1', title: '인터넷 노출 최소화(SG)', status: 'fail', mapped_control: 'INTERNAL-SG-OPEN-INGRESS-001', findings: 1 },
      { code: '2.6.4', title: 'S3 공개 접근 차단', status: 'fail', mapped_control: 'INTERNAL-S3-PUBLIC-001', findings: 1 },
    ] },
    { code: '2.7', name: '암호화', controls: [
      { code: '2.7.3', title: '시크릿 평문 저장 금지', status: 'fail', mapped_control: 'INTERNAL-SECRET-PLAINTEXT-001', findings: 1 },
    ] },
    { code: '3.2', name: '개인정보 보호', controls: [
      { code: '3.2.2', title: '개인정보 공개노출 금지', status: 'fail', mapped_control: 'INTERNAL-DATA-PII-EXPOSED-001', findings: 1 },
    ] },
  ]
  const all = domains.flatMap((d) => d.controls)
  const pass = all.filter((c) => c.status === 'pass').length
  const fail = all.filter((c) => c.status === 'fail').length
  const score = Math.round((pass / Math.max(1, pass + fail)) * 100)
  return { framework: 'ISMS-P (요약 매핑)', generated_at: '2026-06-30T02:20:00Z', score, domains }
}

// ── 실 pgvector 경로(스텁) — USE_MOCK=false + PG_DSN 후 활성화 ──
// eslint 무시: 실배포 시 pg 클라이언트로 findings/attack_paths/cases 테이블 조회.
function pgClientUnavailable(): never {
  throw new Error('real 모드 미구현 — PG_DSN + pg 클라이언트 배선 후 pgFindings 등 구현(콘솔 §5 스키마)')
}
function pgFindings(_f: FindingsFilter): Finding[] { return pgClientUnavailable() }
function pgFindingDetail(_id: string): FindingDetail | null { return pgClientUnavailable() }
function pgAttackPaths(): AttackPath[] { return pgClientUnavailable() }
function pgAttackPath(_id: string): AttackPath | null { return pgClientUnavailable() }
