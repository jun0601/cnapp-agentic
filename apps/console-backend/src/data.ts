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

// ⚠️ 응답 shape·**값**은 프론트 계약(apps/console/src/api/view-types.ts)·프론트 로컬 mock
// (apps/console/src/mocks/view-fixtures.ts)과 정확히 일치해야 함 — audit/compliance는 아직
// contracts로 안 졸업해서 view-fixtures.ts가 사실상 SSOT다. VITE_USE_MOCK=false로 스왑해도
// 화면 숫자(컴플라이언스 점수·감사 건수)가 안 바뀌어야 "MSW→실 API 무변경 스왑"이 성립한다.
// (2026-07-03 검증에서 발견: 이전엔 shape만 맞고 값이 달라 스왑 시 점수·건수가 바뀌는
//  버그가 있었음 — view-fixtures.ts와 항목 수·내용 전부 동일하게 맞춤)
// AuditEvent = {id, ts, actor, role, action, target, result}
export function getAudit() {
  return [
    { id: 'a12', ts: '2026-06-30T02:15:40Z', actor: 'jh_lee@demo', role: 'approver', action: 'approve', target: 'aws:s3_bucket:member-pii-prod', result: 'S3 Public Access Block 적용 → SFn 실행 시작' },
    { id: 'a11', ts: '2026-06-30T02:14:02Z', actor: 'jh_lee@demo', role: 'approver', action: 'view', target: 'case c0000000-…-0001', result: 'Evidence 4건·판정 confirmed 확인' },
    { id: 'a10', ts: '2026-06-30T02:12:30Z', actor: 'jw_kim@demo', role: 'viewer', action: 'reject', target: 'aws:security_group:sg-0product1234', result: '자동 SG 제거 보류 — 변경창구 협의 필요' },
    { id: 'a09', ts: '2026-06-30T02:05:11Z', actor: 'engine', role: 'system', action: 'verdict', target: 'case c0000000-…-0001', result: 'Reasoning confirmed (신뢰도 0.93) — 골든 경로 Critical 정당' },
    { id: 'a08', ts: '2026-06-30T02:03:18Z', actor: 'engine', role: 'system', action: 'verdict', target: 'aws:iam_role:order-irsa', result: 'Evidence: iam:SimulatePrincipalPolicy — 측면이동 경로 확인' },
    { id: 'a07', ts: '2026-06-30T02:03:10Z', actor: 'engine', role: 'system', action: 'verdict', target: 'aws:s3_bucket:member-pii-prod', result: 'Evidence: s3:GetBucketPolicy — 공개 버킷 확인' },
    { id: 'a06', ts: '2026-06-30T02:02:00Z', actor: 'engine', role: 'system', action: 'verdict', target: 'attack_path a0000000-…-0001', result: '트리아지 escalate=true (severity 1 AND attack_path)' },
    { id: 'a05', ts: '2026-06-30T02:00:30Z', actor: 'scanner:macie', role: 'system', action: 'scan', target: 'aws:s3_bucket:member-pii-prod', result: 'SensitiveData:PII 탐지 → f0000000-…-0007' },
    { id: 'a04', ts: '2026-06-30T02:00:12Z', actor: 'scanner:prowler', role: 'system', action: 'scan', target: 'shop/order', result: '평문 Azure SP 시크릿 탐지 → f0000000-…-0005' },
    { id: 'a03', ts: '2026-06-30T02:00:00Z', actor: 'scanner:securityhub', role: 'system', action: 'scan', target: 'batch scan_2026-06-30', result: 'findings 20건 수집 → cnapp.findings.batch.completed 발행' },
    { id: 'a02', ts: '2026-06-30T01:58:40Z', actor: 'jh_lee@demo', role: 'approver', action: 'login', target: 'console', result: 'Entra SSO 로그인 (custom:groups=approver)' },
    { id: 'a01', ts: '2026-06-30T01:50:00Z', actor: 'jw_kim@demo', role: 'viewer', action: 'login', target: 'console', result: 'Entra SSO 로그인 (custom:groups=viewer)' },
  ]
}
// ComplianceReport = {framework, generated_at, score, domains:[{code, name, controls:[{code, title, status, mapped_control?, findings}]}]}
export function getCompliance() {
  const domains = [
    { code: '2.5', name: '인증 및 권한관리', controls: [
      { code: '2.5.1', title: '사용자 MFA 적용', status: 'pass', findings: 0 },
      { code: '2.5.3', title: 'IAM/IRSA 최소권한', status: 'fail', mapped_control: 'INTERNAL-IAM-OVERPRIV-001', findings: 1 },
      { code: '2.5.6', title: 'Entra 앱 과도권한 금지', status: 'fail', mapped_control: 'INTERNAL-ENTRA-OVERPRIV-APP-001', findings: 1 },
    ] },
    { code: '2.6', name: '접근통제', controls: [
      { code: '2.6.1', title: '인터넷 노출 최소화(SG)', status: 'fail', mapped_control: 'INTERNAL-SG-OPEN-INGRESS-001', findings: 1 },
      { code: '2.6.4', title: 'S3 공개 접근 차단', status: 'fail', mapped_control: 'INTERNAL-S3-PUBLIC-001', findings: 1 },
    ] },
    { code: '2.7', name: '암호화', controls: [
      { code: '2.7.1', title: '저장 데이터 암호화(S3 KMS)', status: 'fail', mapped_control: 'INTERNAL-S3-NOENCRYPT-001', findings: 2 },
      { code: '2.7.3', title: '시크릿 평문 저장 금지', status: 'fail', mapped_control: 'INTERNAL-SECRET-PLAINTEXT-001', findings: 1 },
    ] },
    { code: '2.9', name: '로그 및 모니터링', controls: [
      { code: '2.9.1', title: 'CloudTrail 전 리전 수집', status: 'pass', findings: 0 },
      { code: '2.9.4', title: 'S3 접근로깅/버저닝', status: 'fail', mapped_control: 'INTERNAL-S3-LOGGING-DISABLED-001', findings: 1 },
    ] },
    { code: '2.11', name: '취약점 관리', controls: [
      { code: '2.11.1', title: '이미지 취약점(KEV) 차단', status: 'fail', mapped_control: 'INTERNAL-VULN-KEV-001', findings: 1 },
      { code: '2.11.2', title: 'ECR 스캔 활성화', status: 'fail', mapped_control: 'INTERNAL-ECR-SCAN-DISABLED-001', findings: 1 },
      { code: '2.11.5', title: '파드 권한 최소화(KSPM)', status: 'fail', mapped_control: 'INTERNAL-KSPM-PRIVILEGED-001', findings: 1 },
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
