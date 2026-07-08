// OIDC 로그인 — 옵션 B: SPA가 Cognito Hosted UI로 직접 인증(PKCE, public client·시크릿 없음).
//
// 흐름(2026-07-03 확정, infra/console/domain-sso.tf):
//   Login → beginLogin() → Cognito Hosted UI(/oauth2/authorize) → Entra(SAML) → /callback?code=…
//   → completeLogin()이 /oauth2/token에서 code↔토큰 교환(PKCE verifier) → ID 토큰 저장
//   → custom:groups(GUID) 클레임으로 viewer/approver 판정. API 호출엔 Authorization: Bearer <id_token>.
//
// 외부 라이브러리 없이 Web Crypto만 사용(번들 슬림 + Artifact CSP 무관). 서명 검증은 백엔드 책임.
// 빌드 주입(vite env): VITE_COGNITO_DOMAIN·VITE_COGNITO_CLIENT_ID·VITE_REDIRECT_URI
//   = infra/console output(cognito_hosted_ui_domain·spa_cognito_client_id·"https://<도메인>/callback").

export type Role = 'viewer' | 'approver'

// 승인자 그룹 개체 ID(GUID) — console-backend/src/auth.ts와 동일 값(단일 진실은 Entra).
const APPROVER_GROUP_ID = '4d6be000-2a4b-43f7-95ff-cfdb87da786d' // cnapp-approver

const DOMAIN = import.meta.env.VITE_COGNITO_DOMAIN as string | undefined // 예: cnapp-agentic-demo.auth.ap-northeast-2.amazoncognito.com
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined
const REDIRECT_URI =
  (import.meta.env.VITE_REDIRECT_URI as string | undefined) ??
  (typeof location !== 'undefined' ? `${location.origin}/callback` : '')
const SCOPE = 'openid email profile'

const TOKEN_KEY = 'cnapp:oidc:id_token'
const VERIFIER_KEY = 'cnapp:oidc:pkce_verifier'

/** OIDC가 실제로 구성됐는가(도메인·클라이언트ID 주입 여부). 미구성이면 목업/역할선택로 폴백. */
export function oidcConfigured(): boolean {
  return Boolean(DOMAIN && CLIENT_ID)
}

// ── PKCE 헬퍼(Web Crypto) ──────────────────────────────────────────────
function b64url(bytes: Uint8Array): string {
  let s = ''
  for (const b of bytes) s += String.fromCharCode(b)
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function randomVerifier(): string {
  const a = new Uint8Array(32)
  crypto.getRandomValues(a)
  return b64url(a)
}

async function challenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))
  return b64url(new Uint8Array(digest))
}

// ── 로그인 시작: Hosted UI로 리다이렉트 ─────────────────────────────────
export async function beginLogin(): Promise<void> {
  if (!oidcConfigured()) throw new Error('OIDC 미구성(VITE_COGNITO_DOMAIN/CLIENT_ID 없음)')
  const verifier = randomVerifier()
  sessionStorage.setItem(VERIFIER_KEY, verifier)
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: CLIENT_ID!,
    redirect_uri: REDIRECT_URI,
    scope: SCOPE,
    code_challenge_method: 'S256',
    code_challenge: await challenge(verifier),
  })
  location.assign(`https://${DOMAIN}/oauth2/authorize?${params.toString()}`)
}

// ── 콜백: code↔토큰 교환 후 ID 토큰 저장 ────────────────────────────────
export async function completeLogin(): Promise<void> {
  const code = new URLSearchParams(location.search).get('code')
  const verifier = sessionStorage.getItem(VERIFIER_KEY)
  if (!code || !verifier) throw new Error('콜백에 code/PKCE verifier 없음')
  const res = await fetch(`https://${DOMAIN}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: CLIENT_ID!,
      redirect_uri: REDIRECT_URI,
      code,
      code_verifier: verifier,
    }).toString(),
  })
  if (!res.ok) throw new Error(`토큰 교환 실패: ${res.status}`)
  const tok = (await res.json()) as { id_token?: string }
  if (!tok.id_token) throw new Error('응답에 id_token 없음')
  localStorage.setItem(TOKEN_KEY, tok.id_token)
  sessionStorage.removeItem(VERIFIER_KEY)
}

export function logout(): void {
  localStorage.removeItem(TOKEN_KEY)
  if (oidcConfigured()) {
    const params = new URLSearchParams({ client_id: CLIENT_ID!, logout_uri: location.origin })
    location.assign(`https://${DOMAIN}/logout?${params.toString()}`)
  }
}

export function getIdToken(): string | null {
  return typeof localStorage !== 'undefined' ? localStorage.getItem(TOKEN_KEY) : null
}

/** 저장된 ID 토큰만 제거(Cognito 로그아웃 리다이렉트 없이) — 세션 만료 시 조용히 정리용. */
export function clearIdToken(): void {
  if (typeof localStorage !== 'undefined') localStorage.removeItem(TOKEN_KEY)
}

// 시계 오차 여유(30s) — exp 직전 요청이 백엔드 도달 시점엔 만료돼 401 나는 걸 방지(선제 재로그인).
const CLOCK_SKEW_MS = 30_000

/** ID 토큰이 만료됐는가(exp < now+skew). 토큰 없거나 파싱 실패도 만료(=미인증) 취급. */
export function isTokenExpired(): boolean {
  const c = claims()
  const exp = typeof c?.['exp'] === 'number' ? (c['exp'] as number) : 0
  return exp * 1000 <= Date.now() + CLOCK_SKEW_MS
}

/** 유효 세션 = 토큰 있고 아직 안 만료. (기존 '존재만 확인'에서 만료 검사 추가 — 2026-07-08) */
export function isAuthenticated(): boolean {
  return Boolean(getIdToken()) && !isTokenExpired()
}

/** 토큰은 있으나 만료됨 = 세션 만료(재로그인 유도 대상). '처음부터 미로그인'과 구분해 안내를 다르게. */
export function isSessionExpired(): boolean {
  return Boolean(getIdToken()) && isTokenExpired()
}

function claims(): Record<string, unknown> | null {
  const t = getIdToken()
  if (!t) return null
  try {
    const seg = t.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(decodeURIComponent(escape(atob(seg)))) as Record<string, unknown>
  } catch {
    return null
  }
}

/** ID 토큰 custom:groups(GUID)로 역할 판정 — 백엔드 roleFromHeaders와 동일 규칙.
 * ⚠️ 만료 토큰은 approver로 안 봄(백엔드도 서명·exp 검증 실패로 viewer 강등) — 만료됐는데
 *    approver UI가 보여 조치 버튼을 누르면 백엔드 403(→혼란)이 나던 문제 방지(2026-07-08). */
export function roleFromToken(): Role {
  if (isTokenExpired()) return 'viewer'
  const c = claims()
  if (!c) return 'viewer'
  const g = c['custom:groups'] ?? c['cognito:groups'] ?? ''
  const text = Array.isArray(g) ? g.join(',') : String(g)
  return text.includes(APPROVER_GROUP_ID) ? 'approver' : 'viewer'
}

export function userEmail(): string | null {
  const c = claims()
  return (c?.email as string) ?? null
}
