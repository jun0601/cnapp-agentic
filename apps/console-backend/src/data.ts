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
  sources: string[] // ⚠️ 프론트 FindingDetail이 f.sources.join()으로 접근 — 실쿼리에서 빠지면 undefined.join 크래시(2026-07-07)
  priority_score: number | null
  attack_path_id: string | null
  ai_status: string
  first_seen?: string
  last_seen?: string
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
  // Evidence 탭(계약⑦)이 전부 렌더 — 실쿼리에서 빠지면 탭이 반쪽(triage/가설/tool호출수/토큰 누락). 2026-07-07.
  stage?: string
  triage?: unknown
  hypotheses?: unknown[]
  evidence?: unknown[]
  evidence_meta?: unknown
  reasoning?: { narrative?: string; risk_level?: string; recommended_actions?: string[]; rag_refs?: string[] }
  model_trace?: unknown[]
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

// ⚠️ 기본값이 환경에 따라 다르다 — fail-safe 방향 때문.
//   로컬/CI: contracts/*.json이 있으므로 mock이 안전한 기본값(개발 편의).
//   Lambda : 번들에 contracts/가 없어서 mock으로 폴백하면 loadJson의 readFileSync가 그대로 터진다.
//            (2026-07-21 감사에서 발견 — env 주입이 실패하면 크래시하던 경로)
//            그래서 Lambda에선 real이 기본. terraform이 USE_MOCK을 명시 주입하지만 그게 유실돼도 살아남게.
const IN_LAMBDA = Boolean(process.env.AWS_LAMBDA_FUNCTION_NAME)
const USE_MOCK = (process.env.USE_MOCK ?? (IN_LAMBDA ? 'false' : 'true')) !== 'false'
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

// ── 공개 API(핸들러가 호출) — DB-backed 4종은 async(real은 pgvector 조회) ──
export async function getFindings(filter: FindingsFilter): Promise<Finding[]> {
  if (!USE_MOCK) return pgFindings(filter)
  let rows = mockFindings().slice()
  if (filter.cloud) rows = rows.filter((f) => f.cloud === filter.cloud)
  if (filter.pillar) rows = rows.filter((f) => f.pillar === filter.pillar)
  if (filter.status) rows = rows.filter((f) => f.status === filter.status)
  rows.sort(filter.sort === 'severity' ? SEV_SORT : PRIO_SORT)
  return rows
}

export async function getFindingDetail(id: string): Promise<FindingDetail | null> {
  if (!USE_MOCK) return pgFindingDetail(id)
  const f = mockFindings().find((x) => x.finding_id === id)
  if (!f) return null
  const cases = mockCases()
  return { finding: f, explanation: explanationFor(f, cases), case: caseForFinding(id, cases) }
}

export async function getAttackPaths(): Promise<AttackPath[]> {
  return USE_MOCK ? mockPaths() : pgAttackPaths()
}
export async function getAttackPath(id: string): Promise<AttackPath | null> {
  if (!USE_MOCK) return pgAttackPath(id)
  return mockPaths().find((p) => p.attack_path_id === id) ?? null
}

// ── /chat 자연어 질의 → RAG 답변(§8) ─────────────────────────────────
// mock: 템플릿 에코 / real: Titan Embed v2 → pgvector cosine top_k → Sonnet converse.
// rag/(Python)와 동일 파이프라인의 TS판 — 같은 rag_chunks 테이블·같은 Titan 모델(벡터 정합).
const EMBED_MODEL = 'amazon.titan-embed-text-v2:0'
// RAG 답변 모델. 설계 선호=Sonnet 4.5(품질 티어)지만 이 계정 Bedrock에 Sonnet 액세스가
// 아직 미개방(2026-07-06 라이브 확인 — Marketplace subscribe 필요, 관리자 API로도 불가)이라
// 이미 열려 동작하는 Haiku 4.5를 기본값으로. Sonnet 액세스가 열리면 CHAT_MODEL_ID env로 무코드 스왑.
// (엔진 evidence도 같은 Haiku 프로파일 — bedrock_planner.DEFAULT_MODEL_ID와 정합)
const CHAT_MODEL = process.env.CHAT_MODEL_ID ?? 'global.anthropic.claude-haiku-4-5-20251001-v1:0'

export interface ChatRef {
  control: string // 근거 청크의 control_id(예: INTERNAL-S3-PUBLIC-001) — 없으면 chunk_id 앞 8자
  snippet: string // 청크 텍스트 미리보기
}
export async function chatAnswer(q: string): Promise<{ answer: string; refs: ChatRef[] }> {
  if (USE_MOCK || !q) return { answer: `(mock) "${q}" 에 대한 RAG 응답 자리`, refs: [] }

  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { BedrockRuntimeClient, InvokeModelCommand, ConverseCommand } =
    require('@aws-sdk/client-bedrock-runtime') as typeof import('@aws-sdk/client-bedrock-runtime')
  const br = new BedrockRuntimeClient({})

  // 1) 질의 임베딩(Titan v2, 1024-dim) — 적재부와 동일 모델
  const eResp = await br.send(
    new InvokeModelCommand({
      modelId: EMBED_MODEL,
      body: JSON.stringify({ inputText: q, dimensions: 1024, normalize: true }),
    }),
  )
  const embedding = JSON.parse(Buffer.from(eResp.body).toString('utf-8')).embedding as number[]
  const vec = '[' + embedding.map((v) => v.toFixed(6)).join(',') + ']'

  // 2) pgvector cosine top_k
  const r = await (await pool()).query(
    "SELECT chunk_id, text, metadata->>'control_id' AS control_id FROM rag_chunks ORDER BY embedding <=> $1::vector LIMIT 4",
    [vec],
  )
  const chunks = r.rows as { chunk_id: string; text: string; control_id: string | null }[]

  // 3) Sonnet converse(검색 청크를 system 컨텍스트로)
  const context = chunks.map((c, i) => `【지식베이스 ${i + 1}】\n${c.text}`).join('\n\n')
  const cResp = await br.send(
    new ConverseCommand({
      modelId: CHAT_MODEL,
      system: [{ text: `당신은 클라우드 보안 전문가입니다. 아래 지식베이스를 참고해 한국어로 답하세요.\n\n${context}` }],
      messages: [{ role: 'user', content: [{ text: q }] }],
    }),
  )
  const answer = cResp.output?.message?.content?.[0]?.text ?? '(응답 없음)'
  return {
    answer,
    refs: chunks.map((c) => ({
      control: c.control_id ?? `chunk:${c.chunk_id.slice(0, 8)}`,
      snippet: c.text.replace(/\s+/g, ' ').trim().slice(0, 90),
    })),
  }
}

// ── /system — AI·시스템 관측(콘솔에서 "AI가 어떻게 돌아가는지" 한 화면) ─────────
// 모델 구성(챗·임베딩·엔진) + RAG 지식베이스(pgvector) 통계 + Bedrock 사용량(CloudWatch
// AWS/Bedrock 지표 24h 집계) + 데이터 현황. 전부 read-only 관측.
export interface SystemInfo {
  live: boolean
  models: { chat: string; embed: string; engine: string }
  rag: { chunks: number; controls: number; dim: number; index: string }
  bedrock: { invocations24h: number; inputTokens24h: number; outputTokens24h: number } // -1 = 집계 실패
  data: { findingsOpen: number; findingsTotal: number; attackPaths: number; cases: number }
}

export async function getSystem(): Promise<SystemInfo> {
  const models = {
    chat: CHAT_MODEL,
    embed: EMBED_MODEL,
    // 능동조사(Evidence tool-use) 엔진 모델 — backend 레이어 orchestrator와 동일 프로파일(bedrock_planner.DEFAULT_MODEL_ID)
    engine: process.env.ENGINE_MODEL_ID ?? 'global.anthropic.claude-haiku-4-5-20251001-v1:0',
  }
  if (USE_MOCK) {
    const fs = mockFindings()
    return {
      live: false,
      models,
      rag: { chunks: 24, controls: 15, dim: 1024, index: 'HNSW (cosine)' },
      bedrock: { invocations24h: 6, inputTokens24h: 7415, outputTokens24h: 1180 },
      data: {
        findingsOpen: fs.filter((f) => f.status === 'open').length,
        findingsTotal: fs.length,
        attackPaths: mockPaths().length,
        cases: mockCases().length,
      },
    }
  }
  const p = await pool()
  const [rag, fc, ap, cs] = await Promise.all([
    p.query("SELECT count(*)::int AS chunks, count(DISTINCT metadata->>'control_id')::int AS controls FROM rag_chunks"),
    p.query("SELECT count(*)::int AS total, count(*) FILTER (WHERE status = 'open')::int AS open FROM findings"),
    p.query('SELECT count(*)::int AS n FROM attack_paths'),
    p.query('SELECT count(*)::int AS n FROM cases'),
  ])
  return {
    live: true,
    models,
    rag: { chunks: rag.rows[0].chunks, controls: rag.rows[0].controls, dim: 1024, index: 'HNSW (cosine)' },
    bedrock: await bedrockUsage24h(),
    data: {
      findingsOpen: fc.rows[0].open,
      findingsTotal: fc.rows[0].total,
      attackPaths: ap.rows[0].n,
      cases: cs.rows[0].n,
    },
  }
}

// Bedrock 사용량(최근 24h) — CloudWatch AWS/Bedrock 네임스페이스를 GetMetricData SEARCH로 전 모델 합산.
// (SEARCH는 알람에선 미지원이지만 GetMetricData API·대시보드에선 지원 — infra/monitoring §13과 동일 제약 이해)
async function bedrockUsage24h(): Promise<SystemInfo['bedrock']> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { CloudWatchClient, GetMetricDataCommand } =
      require('@aws-sdk/client-cloudwatch') as typeof import('@aws-sdk/client-cloudwatch')
    const cw = new CloudWatchClient({})
    const end = new Date()
    const start = new Date(end.getTime() - 24 * 3600 * 1000)
    const q = (id: string, metric: string) => ({
      Id: id,
      Expression: `SUM(SEARCH('{AWS/Bedrock,ModelId} MetricName="${metric}"', 'Sum', 3600))`,
      Period: 3600,
    })
    const r = await cw.send(
      new GetMetricDataCommand({
        StartTime: start,
        EndTime: end,
        MetricDataQueries: [q('inv', 'Invocations'), q('tin', 'InputTokenCount'), q('tout', 'OutputTokenCount')],
      }),
    )
    const sum = (id: string) =>
      Math.round((r.MetricDataResults?.find((m) => m.Id === id)?.Values ?? []).reduce((a, b) => a + b, 0))
    return { invocations24h: sum('inv'), inputTokens24h: sum('tin'), outputTokens24h: sum('tout') }
  } catch {
    return { invocations24h: -1, inputTokens24h: -1, outputTokens24h: -1 } // 관측 실패는 -1(프론트 '집계 불가' 표시) — 페이지는 산다
  }
}

// ── AI 재조사(라이브 트리거) — orchestrator Lambda 비동기 invoke ────────────────
// 콘솔에서 "AI가 지금 조사한다"를 실연하는 경로: POST /findings/:id/reanalyze →
// backend 레이어 orchestrator(트리아지→Evidence 실 Bedrock tool-use→Reasoning)가 open findings
// 전체를 재조사해 cases·finding_explanations를 갱신(엔진 handler는 이벤트 무관 전체 재실행).
export async function triggerReanalyze(findingId: string): Promise<{ accepted: boolean; mode: 'live' | 'mock' }> {
  if (USE_MOCK) return { accepted: true, mode: 'mock' }
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { LambdaClient, InvokeCommand } = require('@aws-sdk/client-lambda') as typeof import('@aws-sdk/client-lambda')
  await new LambdaClient({}).send(
    new InvokeCommand({
      FunctionName: process.env.ORCHESTRATOR_FN ?? 'cnapp-agentic-orchestrator',
      InvocationType: 'Event', // 조사(tool-use 루프)는 수십 초~분 단위 — 비동기로 던지고 202
      Payload: Buffer.from(JSON.stringify({ source: 'console.reanalyze', finding_id: findingId })),
    }),
  )
  return { accepted: true, mode: 'live' }
}

// ── 조치 승인/거부(HITL) — approve는 실제 Step Functions 실행(engine/remediation.py). ──
// 콘솔은 StartExecution 트리거만(§10·§17 — 실 변경은 격상 역할 Lambda가). approve 흐름:
//   ① finding 조회 → control_id로 조치 액션·타깃 매핑 ② remediation_requests(approved) 기록
//   ③ SFn StartExecution(입력=remediation Lambda event) ④ Lambda가 완료 시 finding=remediated로 UPDATE(점수↑)
// 데모는 '드리프트 없는' 조치만(S3 SSE·ECR scan-on-push) — terraform이 관리 안 하는 속성이라
// 재apply해도 안 꼬임. resource_id의 native_id가 실 리소스명이어야 조치가 실제로 성공한다.
const REMEDIATION_ACTIONS: Record<string, { action: string; targetKey: string }> = {
  'INTERNAL-S3-NOENCRYPT-001': { action: 's3_enable_encryption', targetKey: 'bucket' }, // 드리프트 X
  'INTERNAL-ECR-SCAN-DISABLED-001': { action: 'ecr_enable_scan_on_push', targetKey: 'repository_name' }, // 드리프트 X
  'INTERNAL-S3-PUBLIC-001': { action: 's3_block_public', targetKey: 'bucket' }, // ⚠️ 드리프트 O(target 토글 되돌림)
  'INTERNAL-SG-OPEN-INGRESS-001': { action: 'sg_remove_open_ingress', targetKey: 'security_group_id' }, // ⚠️ 드리프트 O
}
// resource_id = {cloud}:{type}:{native_id} — native_id 추출(ecr repo의 '/'는 유지, 콜론만 구분자).
function nativeId(resourceId: string): string {
  return resourceId.split(':').slice(2).join(':')
}

export interface DecisionResult {
  ok: boolean
  id?: string
  action?: string
  execution_arn?: string
  error?: string
}

export async function decideRemediation(
  findingId: string,
  decision: 'approve' | 'reject',
  approver: string,
): Promise<DecisionResult> {
  if (USE_MOCK) return { ok: true, id: findingId, action: decision }
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { randomUUID } = require('node:crypto') as typeof import('node:crypto')
  const p = await pool()
  const fr = await p.query('SELECT finding_id, control_id, resource_id FROM findings WHERE finding_id = $1', [findingId])
  if (fr.rows.length === 0) return { ok: false, error: 'finding not found' }
  const f = fr.rows[0] as { finding_id: string; control_id: string; resource_id: string }
  const remediationId = randomUUID()

  if (decision === 'reject') {
    await p.query(`INSERT INTO remediation_requests (id, finding_id, status, approver) VALUES ($1, $2, 'rejected', $3)`, [
      remediationId,
      findingId,
      approver,
    ])
    return { ok: true, id: remediationId, action: 'reject' }
  }

  const map = REMEDIATION_ACTIONS[f.control_id]
  if (!map) return { ok: false, error: `자동 조치 미지원 control: ${f.control_id}` }
  const target: Record<string, string> = { [map.targetKey]: nativeId(f.resource_id) }

  // 승인 요청 기록(HITL 감사) → remediation Lambda가 완료 시 status='applied'로 UPDATE.
  await p.query(`INSERT INTO remediation_requests (id, finding_id, status, approver) VALUES ($1, $2, 'approved', $3)`, [
    remediationId,
    findingId,
    approver,
  ])
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { SFNClient, StartExecutionCommand } = require('@aws-sdk/client-sfn') as typeof import('@aws-sdk/client-sfn')
  const sfn = new SFNClient({})
  const input = { remediation_id: remediationId, finding_id: findingId, approver, action: map.action, target, dry_run: false }
  const exec = await sfn.send(new StartExecutionCommand({ stateMachineArn: process.env.SFN_ARN, input: JSON.stringify(input) }))
  await p.query(`UPDATE remediation_requests SET step_function_arn = $1, updated_at = now() WHERE id = $2`, [
    exec.executionArn,
    remediationId,
  ])
  return { ok: true, id: remediationId, action: map.action, execution_arn: exec.executionArn }
}

// scores·audit·compliance — real 모드에선 RDS 실조회(findings/remediation_requests/cases), mock은 정적 픽스처.
// (2026-07-07: 하드코딩 상수 → 실데이터화. ⚠️ AWS Security Hub는 이 계정 구독제약(SubscriptionRequired)으로
//  실점수 불가, Azure Defender secure score는 집계 대기 → 둘 다 '실 open findings 기반 posture'로 산출·라벨 명시.)

// AWS/Azure posture 점수 — open findings의 심각도 가중 패널티로 산출(취약 타깃이라 낮게 나오는 게 정상·정직).
export async function getScores() {
  if (USE_MOCK) {
    return {
      aws: { secure_score: 62, label: 'AWS Security Hub' },
      azure: { secure_score: 74, label: 'Azure Defender / Entra' },
    }
  }
  const r = await (await pool()).query(
    "SELECT cloud, severity_id, count(*)::int AS n FROM findings WHERE status = 'open' GROUP BY cloud, severity_id",
  )
  const W: Record<number, number> = { 1: 8, 2: 4, 3: 2, 4: 1 } // critical..low 심각도 가중
  const penalty: Record<string, number> = {}
  for (const row of r.rows as { cloud: string; severity_id: number; n: number }[]) {
    penalty[row.cloud] = (penalty[row.cloud] ?? 0) + (W[row.severity_id] ?? 1) * row.n
  }
  const score = (c: string) => Math.max(10, Math.min(100, 100 - (penalty[c] ?? 0)))
  return {
    aws: { secure_score: score('aws'), label: '실 open findings 기반 posture' },
    azure: { secure_score: score('azure'), label: '실 open findings 기반 posture' },
  }
}

// AuditEvent = {id, ts, actor, role, action, target, result}
// ⚠️ shape는 프론트 계약(view-types.ts)과 일치해야 함. 단 real 모드는 이제 실 RDS 값을 반환하므로
// mock(아래 MOCK_AUDIT)과 값이 다르다(의도적 — 2026-07-07 실데이터화). MOCK_AUDIT는 dev/CI 픽스처.
const MOCK_AUDIT = [
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

// 감사로그 — real: 실 RDS 기록을 시간순 병합(HITL 조치[remediation_requests]·엔진 판정[cases]·스캔 탐지[findings]).
export async function getAudit() {
  if (USE_MOCK) return MOCK_AUDIT
  const p = await pool()
  const [rem, cs, scans, logins] = await Promise.all([
    p.query(
      `SELECT r.id, r.status, r.approver, r.step_function_arn, r.updated_at, f.resource_id
       FROM remediation_requests r JOIN findings f ON f.finding_id = r.finding_id
       ORDER BY r.updated_at DESC LIMIT 8`,
    ),
    p.query(
      `SELECT case_id, evidence_meta->>'verdict' AS verdict, evidence_meta->>'confidence_score' AS conf, updated_at
       FROM cases WHERE evidence_meta IS NOT NULL ORDER BY updated_at DESC LIMIT 6`,
    ),
    p.query(
      `SELECT finding_id, resource_id, control_id, sources, first_seen
       FROM findings WHERE first_seen IS NOT NULL ORDER BY first_seen DESC LIMIT 10`,
    ),
    // login_events(2026-07-08 신설, Cognito 트리거가 씀) — 스키마 미적용 배포 타이밍이면
    // 테이블이 아직 없을 수 있어 실패해도 감사로그 전체가 안 죽게 개별 catch(빈 배열 폴백).
    p.query(`SELECT id, actor, role, logged_in_at FROM login_events ORDER BY logged_in_at DESC LIMIT 8`)
      .catch(() => ({ rows: [] as Record<string, unknown>[] })),
  ])
  type Ev = { id: string; ts: string; actor: string; role: string; action: string; target: string; result: string }
  const ev: Ev[] = []
  const ACT: Record<string, string> = { approved: 'approve', rejected: 'reject', applied: 'apply', pending: 'request' }
  for (const r of rem.rows as Record<string, unknown>[]) {
    ev.push({
      id: 'r' + String(r.id).slice(0, 8),
      ts: new Date(r.updated_at as string).toISOString(),
      actor: (r.approver as string) ?? 'engine',
      role: r.approver ? 'approver' : 'system',
      action: ACT[r.status as string] ?? (r.status as string),
      target: r.resource_id as string,
      result:
        r.status === 'applied' ? `조치 적용됨${r.step_function_arn ? ' → SFn 실행' : ''}` :
        r.status === 'rejected' ? '조치 반려(변경창구 협의)' : `조치 ${r.status}`,
    })
  }
  for (const c of cs.rows as Record<string, unknown>[]) {
    const conf = c.conf != null ? Math.round(Number(c.conf) * 100) : null
    ev.push({
      id: 'c' + String(c.case_id).slice(0, 8),
      ts: new Date(c.updated_at as string).toISOString(),
      actor: 'engine',
      role: 'system',
      action: 'verdict',
      target: 'case ' + String(c.case_id).slice(0, 8),
      result: `AI 능동조사 판정 ${(c.verdict as string) ?? '—'}${conf != null ? ` (신뢰도 ${conf}%)` : ''}`,
    })
  }
  for (const s of scans.rows as Record<string, unknown>[]) {
    const src = Array.isArray(s.sources) && s.sources[0] ? String(s.sources[0]).split(':')[0] : 'scan'
    ev.push({
      id: 's' + String(s.finding_id).slice(0, 8),
      ts: new Date(s.first_seen as string).toISOString(),
      actor: 'scanner:' + src,
      role: 'system',
      action: 'scan',
      target: s.resource_id as string,
      result: `${s.control_id} 탐지`,
    })
  }
  for (const l of logins.rows as Record<string, unknown>[]) {
    ev.push({
      id: 'l' + String(l.id).slice(0, 8),
      ts: new Date(l.logged_in_at as string).toISOString(),
      actor: l.actor as string,
      role: l.role as string,
      action: 'login',
      target: 'console',
      result: `Entra SSO 로그인 (${l.role})`,
    })
  }
  ev.sort((a, b) => (a.ts < b.ts ? 1 : a.ts > b.ts ? -1 : 0))
  return ev.slice(0, 18)
}
// ComplianceReport = {framework, generated_at, score, domains:[{code, name, controls:[{code, title, status, mapped_control?, findings}]}]}
// 프레임워크↔control 매핑(ISMS-P)은 표준 정의라 정적. status·findings·score는 real 모드에서 실 findings 집계
// (control별 open finding 수 → 있으면 fail·건수, 없으면 pass). 조치로 finding이 사라지면 해당 통제가 pass로 바뀜.
type CtlDef = { code: string; title: string; mapped_control?: string }
const ISMS_STRUCT: { code: string; name: string; controls: CtlDef[] }[] = [
  { code: '2.5', name: '인증 및 권한관리', controls: [
    { code: '2.5.1', title: '사용자 MFA 적용' },
    { code: '2.5.3', title: 'IAM/IRSA 최소권한', mapped_control: 'INTERNAL-IAM-OVERPRIV-001' },
    { code: '2.5.6', title: 'Entra 앱 과도권한 금지', mapped_control: 'INTERNAL-ENTRA-OVERPRIV-APP-001' },
  ] },
  { code: '2.6', name: '접근통제', controls: [
    { code: '2.6.1', title: '인터넷 노출 최소화(SG)', mapped_control: 'INTERNAL-SG-OPEN-INGRESS-001' },
    { code: '2.6.4', title: 'S3 공개 접근 차단', mapped_control: 'INTERNAL-S3-PUBLIC-001' },
  ] },
  { code: '2.7', name: '암호화', controls: [
    { code: '2.7.1', title: '저장 데이터 암호화(S3 KMS)', mapped_control: 'INTERNAL-S3-NOENCRYPT-001' },
    { code: '2.7.3', title: '시크릿 평문 저장 금지', mapped_control: 'INTERNAL-SECRET-PLAINTEXT-001' },
  ] },
  { code: '2.9', name: '로그 및 모니터링', controls: [
    { code: '2.9.1', title: 'CloudTrail 전 리전 수집' },
    { code: '2.9.4', title: 'S3 접근로깅/버저닝', mapped_control: 'INTERNAL-S3-LOGGING-DISABLED-001' },
  ] },
  { code: '2.11', name: '취약점 관리', controls: [
    { code: '2.11.1', title: '이미지 취약점(KEV) 차단', mapped_control: 'INTERNAL-VULN-KEV-001' },
    { code: '2.11.2', title: 'ECR 스캔 활성화', mapped_control: 'INTERNAL-ECR-SCAN-DISABLED-001' },
    { code: '2.11.5', title: '파드 권한 최소화(KSPM)', mapped_control: 'INTERNAL-KSPM-PRIVILEGED-001' },
  ] },
  { code: '3.2', name: '개인정보 보호', controls: [
    { code: '3.2.2', title: '개인정보 공개노출 금지', mapped_control: 'INTERNAL-DATA-PII-EXPOSED-001' },
  ] },
]
// mock 모드 open 건수(view-fixtures.ts와 동일 — dev/CI 일관성)
const MOCK_OPEN_BY_CONTROL: Record<string, number> = {
  'INTERNAL-IAM-OVERPRIV-001': 1, 'INTERNAL-ENTRA-OVERPRIV-APP-001': 1,
  'INTERNAL-SG-OPEN-INGRESS-001': 1, 'INTERNAL-S3-PUBLIC-001': 1,
  'INTERNAL-S3-NOENCRYPT-001': 2, 'INTERNAL-SECRET-PLAINTEXT-001': 1,
  'INTERNAL-S3-LOGGING-DISABLED-001': 1, 'INTERNAL-VULN-KEV-001': 1,
  'INTERNAL-ECR-SCAN-DISABLED-001': 1, 'INTERNAL-KSPM-PRIVILEGED-001': 1,
  'INTERNAL-DATA-PII-EXPOSED-001': 1,
}
export async function getCompliance() {
  let openBy: Map<string, number>
  if (USE_MOCK) {
    openBy = new Map(Object.entries(MOCK_OPEN_BY_CONTROL))
  } else {
    const r = await (await pool()).query(
      "SELECT control_id, count(*) FILTER (WHERE status = 'open')::int AS n FROM findings GROUP BY control_id",
    )
    openBy = new Map((r.rows as { control_id: string; n: number }[]).map((x) => [x.control_id, x.n]))
  }
  const domains = ISMS_STRUCT.map((d) => ({
    code: d.code,
    name: d.name,
    controls: d.controls.map((c) => {
      const n = c.mapped_control ? openBy.get(c.mapped_control) ?? 0 : 0
      return {
        code: c.code,
        title: c.title,
        ...(c.mapped_control ? { mapped_control: c.mapped_control } : {}),
        status: n > 0 ? 'fail' : 'pass',
        findings: n,
      }
    }),
  }))
  const all = domains.flatMap((d) => d.controls)
  const pass = all.filter((c) => c.status === 'pass').length
  const fail = all.filter((c) => c.status === 'fail').length
  const score = Math.round((pass / Math.max(1, pass + fail)) * 100)
  return {
    framework: 'ISMS-P (요약 매핑)',
    generated_at: USE_MOCK ? '2026-06-30T02:20:00Z' : new Date().toISOString(),
    score,
    domains,
  }
}

// ── 실 pgvector 경로 — USE_MOCK=false. 스키마=infra/shared/db/schema.sql ──
// 자격증명: PG_DSN(직접) 또는 DB_HOST+DB_SECRET_ARN(Secrets Manager, VPC Lambda 표준).
// pg는 지연 require(mock/CI 번들엔 불필요) — 실배포 시 layer/번들에 포함.
import type { Pool as PgPool } from 'pg'

let _pool: PgPool | null = null
async function pool(): Promise<PgPool> {
  if (_pool) return _pool
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { Pool } = require('pg') as typeof import('pg')
  const dsn = process.env.PG_DSN
  if (dsn) {
    _pool = new Pool({ connectionString: dsn, max: 2, ssl: { rejectUnauthorized: false } })
  } else {
    // Secrets Manager에서 자격증명 로드(engine/pipeline Lambda와 동일 패턴).
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager')
    const sm = new SecretsManagerClient({})
    const sec = JSON.parse(
      (await sm.send(new GetSecretValueCommand({ SecretId: process.env.DB_SECRET_ARN }))).SecretString,
    ) as { username: string; password: string; dbname?: string }
    _pool = new Pool({
      host: process.env.DB_HOST, port: 5432, database: sec.dbname ?? 'cnapp',
      user: sec.username, password: sec.password, max: 2, ssl: { rejectUnauthorized: false },
    })
  }
  return _pool
}

// ⚠️ 프론트가 접근하는 필드는 여기서 전부 SELECT해야 함(빠지면 실데이터에서 undefined → 크래시).
//   sources = FindingDetail의 f.sources.join(), first_seen/last_seen = 계약① 필수 필드.
const F_COLS =
  'finding_id, cloud, resource_id, resource_type, pillar, control_id, title, severity_id, status, sources, priority_score, attack_path_id, ai_status, first_seen, last_seen'

async function pgFindings(f: FindingsFilter): Promise<Finding[]> {
  const where: string[] = []
  const args: unknown[] = []
  for (const [col, val] of [['cloud', f.cloud], ['pillar', f.pillar], ['status', f.status]] as const) {
    if (val) { args.push(val); where.push(`${col} = $${args.length}`) }
  }
  const order = f.sort === 'severity' ? 'severity_id ASC' : 'priority_score DESC NULLS LAST'
  const sql = `SELECT ${F_COLS} FROM findings ${where.length ? 'WHERE ' + where.join(' AND ') : ''} ORDER BY ${order}`
  return (await (await pool()).query(sql, args)).rows as Finding[]
}

async function pgFindingDetail(id: string): Promise<FindingDetail | null> {
  const p = await pool()
  const fr = await p.query(`SELECT ${F_COLS} FROM findings WHERE finding_id = $1`, [id])
  if (fr.rowCount === 0) return null
  const finding = fr.rows[0] as Finding
  // finding_explanations 조인(계약: ai_summary·confidence_score·case_id). ai_status≠done이면 빈 설명.
  const er = await p.query(
    'SELECT ai_summary, confidence_score, rag_refs, case_id, ai_status FROM finding_explanations WHERE finding_id = $1',
    [id],
  )
  const e = er.rows[0] as
    | { ai_summary: string; confidence_score: number | null; case_id: string | null; ai_status: string }
    | undefined
  let caseObj: Case | null = null
  if (e?.case_id) {
    // Evidence 탭이 전 필드 렌더 — triage·hypotheses·evidence_meta·model_trace·stage까지 다 가져와야 반쪽 안 됨.
    const cr = await p.query(
      'SELECT case_id, finding_ids, stage, triage, hypotheses, evidence, evidence_meta, reasoning, model_trace FROM cases WHERE case_id = $1',
      [e.case_id],
    )
    const row = cr.rows[0] as
      | {
          case_id: string; finding_ids: string[]; stage: string; triage: unknown; hypotheses: unknown
          evidence: unknown; evidence_meta: unknown; reasoning: unknown; model_trace: unknown
        }
      | undefined
    if (row) {
      caseObj = {
        case_id: row.case_id,
        finding: { finding_ids: row.finding_ids },
        stage: row.stage,
        triage: row.triage ?? undefined,
        hypotheses: (row.hypotheses as unknown[]) ?? [],
        evidence: (row.evidence as unknown[]) ?? [],
        evidence_meta: row.evidence_meta ?? undefined,
        reasoning:
          (row.reasoning as { narrative?: string; risk_level?: string; recommended_actions?: string[]; rag_refs?: string[] }) ??
          undefined,
        model_trace: (row.model_trace as unknown[]) ?? [],
      }
    }
  }
  const explanation: FindingExplanation =
    e && e.ai_status === 'done'
      ? {
          finding_id: id,
          summary: caseObj?.reasoning?.risk_level
            ? `${finding.title} — control ${finding.control_id} 위반(${finding.pillar}) · 위험도 ${caseObj.reasoning.risk_level}`
            : `${finding.title} — control ${finding.control_id} 위반(${finding.pillar}).`,
          why: caseObj?.reasoning?.narrative ?? e.ai_summary,
          // 엔진 Reasoning 단계가 낸 실제 권고안을 쓴다.
          // (2026-07-21 이전엔 여기가 '조치 카탈로그 참조…' 상수여서, real 모드인데도 AI 설명 3필드 중
          //  2개가 하드코딩이었다 — 감사에서 발견. recommended_actions가 비면 그때만 안내 문구로 폴백.)
          how:
            caseObj?.reasoning?.recommended_actions?.length
              ? caseObj.reasoning.recommended_actions.map((a, i) => `${i + 1}. ${a}`).join('\n')
              : '권고안 미생성 — 조치 카탈로그(§14) 참조. 모든 변경은 승인 경로(HITL)로만 적용.',
          ai_status: 'done',
          case_id: e.case_id,
        }
      : { finding_id: id, summary: '', why: '', how: '', ai_status: e?.ai_status ?? finding.ai_status, case_id: e?.case_id ?? null }
  return { finding, explanation, case: caseObj }
}

async function pgAttackPaths(): Promise<AttackPath[]> {
  return (
    await (await pool()).query(
      'SELECT attack_path_id, severity_id, nodes, edges, narrative_text FROM attack_paths ORDER BY severity_id ASC',
    )
  ).rows as AttackPath[]
}

async function pgAttackPath(id: string): Promise<AttackPath | null> {
  const r = await (await pool()).query(
    'SELECT attack_path_id, severity_id, nodes, edges, narrative_text FROM attack_paths WHERE attack_path_id = $1',
    [id],
  )
  return (r.rows[0] as AttackPath) ?? null
}
