// Cognito Post-Authentication Lambda 트리거 — 로그인 성공마다 RDS(login_events)에 1행 기록.
// 실 감사로그(감사로그 페이지)에 "누가 언제 로그인했는지"가 비어있던 갭을 메운다(2026-07-08).
//
// ⚠️ Cognito 트리거 계약: 이 Lambda가 예외를 던지면(reject) 사용자 로그인 자체가 실패한다.
// 감사 기록 실패는 절대 로그인을 막으면 안 되므로(fail-open) 모든 로직을 try/catch로 감싸고
// 무슨 일이 있어도 event를 그대로 반환한다. console-backend(handler.ts/data.ts)와 완전히
// 분리된 별도 Lambda·별도 esbuild 번들(package.json build 스크립트) — 여기서 에러가 나도
// findings API 등 다른 기능에는 영향 없음.
import { randomUUID } from 'node:crypto'

const APPROVER_GROUP_ID = '4d6be000-2a4b-43f7-95ff-cfdb87da786d' // cnapp-approver (auth.ts와 동일 GUID)

interface CognitoPostAuthEvent {
  userName?: string
  request?: { userAttributes?: Record<string, string> }
  response?: Record<string, unknown>
  [k: string]: unknown
}

function roleFromAttributes(attrs: Record<string, string>): 'viewer' | 'approver' {
  const groups = attrs['custom:groups'] ?? ''
  return groups.includes(APPROVER_GROUP_ID) ? 'approver' : 'viewer'
}

async function recordLogin(actor: string, role: string): Promise<void> {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { Pool } = require('pg') as typeof import('pg')
  const dsn = process.env.PG_DSN
  let pool: InstanceType<typeof Pool>
  if (dsn) {
    pool = new Pool({ connectionString: dsn, max: 1, ssl: { rejectUnauthorized: false } })
  } else {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager')
    const sm = new SecretsManagerClient({})
    const sec = JSON.parse(
      (await sm.send(new GetSecretValueCommand({ SecretId: process.env.DB_SECRET_ARN }))).SecretString,
    ) as { username: string; password: string; dbname?: string }
    pool = new Pool({
      host: process.env.DB_HOST,
      port: 5432,
      database: sec.dbname ?? 'cnapp',
      user: sec.username,
      password: sec.password,
      max: 1,
      ssl: { rejectUnauthorized: false },
    })
  }
  try {
    await pool.query('INSERT INTO login_events (id, actor, role, logged_in_at) VALUES ($1, $2, $3, now())', [
      randomUUID(),
      actor,
      role,
    ])
  } finally {
    await pool.end()
  }
}

// Teams 알림 — 2026-07-08: Azure signIns API 기반 실시간 로그인 알림을 시도했으나 테넌트가
// Azure AD Premium P1 라이선스가 없어 HTTP 403(Authentication_RequestFromNonPremiumTenantOrB2CTenant)
// 으로 구조적으로 막힘(troubleshooting.md 참고) — 대안으로 여기서 직접 Teams에 알림을 보낸다.
// Entra Graph API를 전혀 안 거치므로 라이선스 제약 자체가 적용되지 않고, Cognito가 SAML
// 인증을 이미 완료한 시점에 정확히 트리거되는 이벤트 기반이라 폴링보다 지연·누락이 없다.
// AWS login_notifier.py의 _to_kst()와 동일한 포맷("YYYY-MM-DD HH:MM:SS KST") — 채널이 같으니
// 메시지 포맷도 통일.
function toKstString(date: Date): string {
  const kst = new Date(date.getTime() + 9 * 60 * 60 * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${kst.getUTCFullYear()}-${pad(kst.getUTCMonth() + 1)}-${pad(kst.getUTCDate())} ` +
    `${pad(kst.getUTCHours())}:${pad(kst.getUTCMinutes())}:${pad(kst.getUTCSeconds())} KST`
  )
}

async function notifyTeams(actor: string, role: string): Promise<void> {
  const secretId = process.env.TEAMS_WEBHOOK_SECRET_ID
  if (!secretId) return
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager')
  const sm = new SecretsManagerClient({})
  const webhook = (await sm.send(new GetSecretValueCommand({ SecretId: secretId }))).SecretString
  if (!webhook) return
  const when = toKstString(new Date())
  const text =
    `<b>\u{1F510} 관제 콘솔</b> 로그인 감지<br><br>` +
    `사용자: <b>${actor}</b><br>역할: ${role}<br>시각(KST): ${when}`
  await postWithRetry(webhook, text)
}

// 2026-07-10: cnapp-alerts(SNS 경유, 재시도 보장)와 달리 이 채널은 SNS 없이 직접 POST해
// 재시도 안전망이 없었다 — 웹훅이 순간적으로 실패하면 로그인 알림이 조용히 누락됨.
// 짧은 재시도 3회(1s/2s 대기)로 일시적 네트워크/웹훅 오류를 흡수(호출부는 이미 fail-open이라
// 여기서 다 실패해도 로그인은 막지 않음 — 알림 신뢰성만 개선).
async function postWithRetry(webhook: string, text: string): Promise<void> {
  let lastErr: unknown
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch(webhook, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      if (!res.ok) throw new Error(`webhook POST ${res.status}`)
      return
    } catch (e) {
      lastErr = e
      if (attempt < 2) await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)))
    }
  }
  throw lastErr
}

export async function handler(event: CognitoPostAuthEvent): Promise<CognitoPostAuthEvent> {
  const attrs = event?.request?.userAttributes ?? {}
  const actor = attrs['email'] ?? event?.userName ?? 'unknown'
  const role = roleFromAttributes(attrs)
  try {
    await recordLogin(actor, role)
  } catch (e) {
    // 감사 기록 실패 — 로그로만 남기고 로그인은 절대 막지 않는다(fail-open).
    console.error('login-trigger: audit write failed (login proceeds regardless):', e)
  }
  try {
    await notifyTeams(actor, role)
  } catch (e) {
    console.error('login-trigger: teams notify failed (login proceeds regardless):', e)
  }
  return event
}
