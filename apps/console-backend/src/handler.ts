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

// ⚠️ ALB는 statusDescription을 "<코드> <사유구>"(예: "200 OK") 형식으로 요구한다.
// "200"만 주면 ALB가 응답을 거부해 502를 낸다(2026-07-04 라이브 실측 — Lambda는 정상인데 ALB만 502).
const REASON: Record<number, string> = { 200: 'OK', 202: 'Accepted', 204: 'No Content', 400: 'Bad Request', 403: 'Forbidden', 404: 'Not Found', 500: 'Internal Server Error' }

// CORS — CloudFront 오리진(도메인)만 화이트리스트(와일드카드 * 금지, §보안 하드닝 #4).
// 정상 흐름은 CloudFront /api 프록시라 same-origin이라 CORS가 발동하지 않지만, 직접 호출/프리플라이트에
// 방어적으로 특정 오리진만 명시. 허용 오리진 = infra/console이 ALLOWED_ORIGIN env로 주입(기본 커스텀 도메인).
const ALLOWED_ORIGIN = process.env.ALLOWED_ORIGIN ?? 'https://cnapp-agentic.cloud'
const corsHeaders = (): Record<string, string> => ({
  'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
  'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
  'Access-Control-Allow-Headers': 'Authorization,Content-Type',
  Vary: 'Origin',
})
const json = (statusCode: number, body: unknown): AlbResult => ({
  statusCode,
  statusDescription: `${statusCode} ${REASON[statusCode] ?? 'OK'}`,
  isBase64Encoded: false,
  headers: { 'Content-Type': 'application/json; charset=utf-8', ...corsHeaders() },
  body: JSON.stringify(body),
})

export async function handler(event: AlbEvent): Promise<AlbResult> {
  const method = (event.httpMethod || 'GET').toUpperCase()
  // ALB 리스너가 /api/* 로 라우팅하면 접두 제거(프론트 API_BASE 기본 /api)
  const path = (event.path || '/').replace(/^\/api(?=\/|$)/, '') || '/'
  const q = event.queryStringParameters ?? {}

  // CORS 프리플라이트(브라우저 OPTIONS) — 본문 없이 CORS 헤더만 반환.
  if (method === 'OPTIONS') {
    return { statusCode: 204, statusDescription: '204 No Content', isBase64Encoded: false, headers: corsHeaders(), body: '' }
  }

  try {
    // ── GET ──
    if (method === 'GET') {
      if (path === '/findings') {
        return json(200, await data.getFindings({ cloud: q.cloud, pillar: q.pillar, status: q.status, sort: q.sort }))
      }
      const fDetail = path.match(/^\/findings\/([^/]+)$/)
      if (fDetail) {
        const d = await data.getFindingDetail(decodeURIComponent(fDetail[1]))
        return d ? json(200, d) : json(404, { error: 'finding not found' })
      }
      if (path === '/attack-paths') return json(200, await data.getAttackPaths())
      const pDetail = path.match(/^\/attack-paths\/([^/]+)$/)
      if (pDetail) {
        const p = await data.getAttackPath(decodeURIComponent(pDetail[1]))
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
        if ((await roleFromHeaders(event.headers)) !== 'approver') {
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
        // 자연어 질의 → RAG(Titan 임베딩 → pgvector → Sonnet). mock이면 템플릿 에코.
        return json(200, await data.chatAnswer(body.q ?? ''))
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
