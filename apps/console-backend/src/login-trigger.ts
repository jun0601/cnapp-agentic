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

export async function handler(event: CognitoPostAuthEvent): Promise<CognitoPostAuthEvent> {
  try {
    const attrs = event?.request?.userAttributes ?? {}
    const actor = attrs['email'] ?? event?.userName ?? 'unknown'
    const role = roleFromAttributes(attrs)
    await recordLogin(actor, role)
  } catch (e) {
    // 감사 기록 실패 — 로그로만 남기고 로그인은 절대 막지 않는다(fail-open).
    console.error('login-trigger: audit write failed (login proceeds regardless):', e)
  }
  return event
}
