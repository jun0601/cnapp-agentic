// 역할(RBAC) 추출 — Entra 그룹 클레임 → viewer/approver (console-app-design §7).
// ALB(authenticate-cognito)가 검증한 신원을 x-amzn-oidc-data 헤더(JWT)로 전달 →
// custom:groups 클레임에서 cnapp-approver 그룹이면 approver, 아니면 viewer.
// 조치 승인(POST /remediations)은 approver만(HITL, 거버넌스 §17).
//
// ⚠️ 그룹 "이름" 문자열이 아니라 "개체 ID(GUID)"로 매칭한다(2026-07-02 확정):
// Entra 무료 티어라 SAML 그룹 클레임에서 "애플리케이션에 할당된 그룹"(그룹 이름 내보내기 지원)을
// 못 쓰고(P1/P2 필요) "보안 그룹" 모드를 쓰는데, 이 모드는 클라우드 전용 그룹의 이름 내보내기를
// 지원 안 해 항상 그룹 ID(GUID)만 나온다. 어차피 이름보다 불변 식별자(GUID) 매칭이 더 견고함.
const APPROVER_GROUP_ID = '4d6be000-2a4b-43f7-95ff-cfdb87da786d' // cnapp-approver
// const VIEWER_GROUP_ID = '4d9b6544-47ea-495e-99be-8943362d6bc7' // cnapp-viewer (approver 아니면 기본 viewer라 미사용)

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
    return text.includes(APPROVER_GROUP_ID) ? 'approver' : 'viewer'
  } catch {
    return 'viewer'
  }
}
