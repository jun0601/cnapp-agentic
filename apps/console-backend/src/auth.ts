// 역할(RBAC) 추출 — Entra 그룹 클레임 → viewer/approver (console-app-design §7).
// 두 인증 경로를 모두 지원한다(어느 쪽이든 custom:groups GUID로 판정):
//   ① 옵션 B(현행): SPA가 Cognito Hosted UI로 직접 OIDC → ID 토큰을 Authorization: Bearer로 전송.
//   ② (레거시) ALB authenticate-cognito가 x-amzn-oidc-data 헤더(JWT)로 전달.
// 조치 승인(POST /remediations)은 approver만(HITL, 거버넌스 §17).
//
// 🔐 보안 하드닝(2026-07-06): Bearer(ID 토큰)는 이제 '검증'한다 — Cognito JWKS로 서명·issuer·
//    audience·exp를 aws-jwt-verify로 확인(위조/만료 토큰으로 approver 권한 상승 차단). 이전엔
//    디코드만 해서, 공격자가 custom:groups=approver GUID를 넣은 가짜 JWT로 조치 승인이 가능했음.
//    검증기 미구성(env 없음)이거나 검증 실패 시 fail-closed = 최소 권한(viewer)으로 강등.
//   · env COGNITO_USER_POOL_ID·COGNITO_CLIENT_ID(SPA 앱 클라이언트) = infra/console에서 주입.
//   · x-amzn-oidc-data(레거시)는 ALB가 이미 서명 검증한 신뢰 헤더라 디코드만(이 경로는 옵션B에선 비활성).
//
// ⚠️ 그룹 "이름" 문자열이 아니라 "개체 ID(GUID)"로 매칭한다(2026-07-02 확정):
// Entra 무료 티어라 SAML 그룹 클레임에서 "애플리케이션에 할당된 그룹"(그룹 이름 내보내기 지원)을
// 못 쓰고(P1/P2 필요) "보안 그룹" 모드를 쓰는데, 이 모드는 클라우드 전용 그룹의 이름 내보내기를
// 지원 안 해 항상 그룹 ID(GUID)만 나온다. 어차피 이름보다 불변 식별자(GUID) 매칭이 더 견고함.
import { CognitoJwtVerifier } from 'aws-jwt-verify'

const APPROVER_GROUP_ID = '4d6be000-2a4b-43f7-95ff-cfdb87da786d' // cnapp-approver
// const VIEWER_GROUP_ID = '4d9b6544-47ea-495e-99be-8943362d6bc7' // cnapp-viewer (approver 아니면 기본 viewer라 미사용)

export type Role = 'viewer' | 'approver'

const USER_POOL_ID = process.env.COGNITO_USER_POOL_ID
const CLIENT_ID = process.env.COGNITO_CLIENT_ID // SPA 앱 클라이언트(Bearer ID 토큰의 aud)

// Cognito ID 토큰 검증기 — 지연 생성(JWKS를 최초 verify 시 한 번 받아 캐시). env 없으면 null(fail-closed).
type Verifier = ReturnType<typeof CognitoJwtVerifier.create>
let _verifier: Verifier | null = null
function verifier(): Verifier | null {
  if (!USER_POOL_ID || !CLIENT_ID) return null
  if (!_verifier) {
    _verifier = CognitoJwtVerifier.create({ userPoolId: USER_POOL_ID, tokenUse: 'id', clientId: CLIENT_ID })
  }
  return _verifier
}

function b64urlDecode(seg: string): string {
  const b64 = seg.replace(/-/g, '+').replace(/_/g, '/')
  return Buffer.from(b64, 'base64').toString('utf-8')
}

function roleFromGroups(payload: Record<string, unknown>): Role {
  const groups = payload['custom:groups'] ?? payload['cognito:groups'] ?? ''
  const text = Array.isArray(groups) ? groups.join(',') : String(groups)
  return text.includes(APPROVER_GROUP_ID) ? 'approver' : 'viewer'
}

export async function roleFromHeaders(headers: Record<string, string | undefined> = {}): Promise<Role> {
  // 헤더 키는 대소문자 혼용 가능 → 소문자로 정규화
  const lower: Record<string, string> = {}
  for (const [k, v] of Object.entries(headers)) if (v != null) lower[k.toLowerCase()] = v

  // ① Authorization: Bearer <id_token> (옵션 B, SPA 직접 OIDC) — Cognito JWKS로 '검증'
  const bearer = lower['authorization']?.replace(/^Bearer\s+/i, '')
  if (bearer) {
    const v = verifier()
    if (!v) return 'viewer' // 검증기 미구성(env 없음) → fail-closed
    try {
      const payload = (await v.verify(bearer)) as unknown as Record<string, unknown>
      return roleFromGroups(payload)
    } catch {
      return 'viewer' // 서명·iss·aud·exp 검증 실패(위조/만료) → 최소 권한
    }
  }

  // ② x-amzn-oidc-data (레거시 ALB authenticate-cognito) — ALB가 이미 서명 검증한 신뢰 헤더라 디코드만.
  //    이 경로는 옵션 B(현행)에선 도달하지 않음(ALB 인증 게이트 비활성).
  const albJwt = lower['x-amzn-oidc-data']
  if (albJwt) {
    try {
      const parts = albJwt.split('.')
      if (parts.length < 2) return 'viewer'
      const payload = JSON.parse(b64urlDecode(parts[1])) as Record<string, unknown>
      return roleFromGroups(payload)
    } catch {
      return 'viewer'
    }
  }

  return 'viewer' // 미인증/로컬 mock → 최소 권한 기본값
}
