// 타입드 fetch 래퍼. MOCK=true면 MSW가 이 요청을 가로챈다(§15.5 스왑 포인트).
// 실데이터 전환: VITE_USE_MOCK=false + VITE_API_BASE=ALB URL, 이 파일은 무변경.

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function apiGet<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  const qs = params
    ? '?' +
      new URLSearchParams(
        Object.entries(params).filter(([, v]) => v != null) as [string, string][],
      ).toString()
    : ''
  const res = await fetch(`${API_BASE}${path}${qs}`, {
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) throw new ApiError(res.status, `GET ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new ApiError(res.status, `POST ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

export { API_BASE }
