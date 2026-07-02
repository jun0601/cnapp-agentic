// 역할(RBAC) 추출 — Entra 그룹 클레임 → viewer/approver (console-app-design §7).
// ALB(authenticate-cognito)가 검증한 신원을 x-amzn-oidc-data 헤더(JWT)로 전달 →
// custom:groups 클레임에서 cnapp-approver면 approver, 아니면 viewer.
// 조치 승인(POST /remediations)은 approver만(HITL, 거버넌스 §17).

export type Role = 'viewer' | 'approver'

function b64urlDecode(seg: string): string {
  const b64 = seg.replace(/-/g, '+').replace(/_/g, '/')
  return Buffer.from(b64, 'base64').toString('utf-8')
}

export function roleFromHeaders(headers: Record<string, string | undefined> = {}): Role {
  // 헤더 키는 대소문자 혼용 가능 → 소문자로 정규화
  const lower: Record<string, string> = {}
  for (const [k, v] of Object.entries(headers)) if (v != null) lower[k.toLowerCase()] = v
  const jwt = lower['x-amzn-oidc-data']
  if (!jwt) return 'viewer' // 미인증/로컬 mock → 최소 권한 기본값
  try {
    const parts = jwt.split('.')
    if (parts.length < 2) return 'viewer'
    const payload = JSON.parse(b64urlDecode(parts[1])) as Record<string, unknown>
    const groups = payload['custom:groups'] ?? payload['cognito:groups'] ?? ''
    const text = Array.isArray(groups) ? groups.join(',') : String(groups)
    return text.includes('cnapp-approver') ? 'approver' : 'viewer'
  } catch {
    return 'viewer'
  }
}
