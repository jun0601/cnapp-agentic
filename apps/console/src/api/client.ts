// 타입드 fetch 래퍼. MOCK=true면 MSW가 이 요청을 가로챈다(§15.5 스왑 포인트).
// 실데이터 전환: VITE_USE_MOCK=false + VITE_API_BASE=ALB URL.
// 옵션 B(SPA 직접 OIDC): OIDC ID 토큰을 Authorization: Bearer로 실어 보낸다 → 백엔드가 역할 판정.
import { getIdToken } from '@/lib/oidc'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

function authHeaders(): Record<string, string> {
  const t = getIdToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

// CloudFront custom_error_response(403/404 → 200 index.html)가 API 에러를 SPA 껍데기로 가리는
// 함정 방어(2026-07-08): res.ok(200)여도 본문이 JSON이 아니라 text/html이면 CloudFront가
// 백엔드 에러(대개 만료·미인증 403)를 index.html로 바꾼 것 → 인증 문제로 명확히 던져 UI가
// 재로그인을 유도하게 한다(그냥 res.json()하면 "Unexpected token '<'"라는 알 수 없는 에러로 보임).
async function parseJson<T>(res: Response, path: string): Promise<T> {
  const ctype = res.headers.get('content-type') ?? ''
  if (!ctype.includes('application/json')) {
    throw new ApiError(res.status === 200 ? 401 : res.status, `${path} → 비JSON 응답(세션 만료/권한 문제 가능)`)
  }
  return res.json() as Promise<T>
}

export async function apiGet<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  const qs = params
    ? '?' +
      new URLSearchParams(
        Object.entries(params).filter(([, v]) => v != null) as [string, string][],
      ).toString()
    : ''
  const res = await fetch(`${API_BASE}${path}${qs}`, {
    headers: { Accept: 'application/json', ...authHeaders() },
  })
  if (!res.ok) throw new ApiError(res.status, `GET ${path} → ${res.status}`)
  return parseJson<T>(res, `GET ${path}`)
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new ApiError(res.status, `POST ${path} → ${res.status}`)
  return parseJson<T>(res, `POST ${path}`)
}

export { API_BASE }
