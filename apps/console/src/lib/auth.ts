// 역할(§7 RBAC — viewer/approver). 목업 단계선 placeholder.
// 실연동(진우 확정): Entra SAML attr → Cognito custom:groups → ALB(authenticate-cognito)가
// x-amzn-oidc-data JWT로 실어 보냄 → 역할 판정은 console-backend(Lambda)에서 수행.
// 프론트는 AWS를 직접 호출하지 않으므로(Identity Pool 미사용) 여기선 백엔드가 내려준 역할을 표시만 한다.

export type Role = 'viewer' | 'approver'

export function getRole(): Role {
  // TODO: 실데이터 전환 시 백엔드가 x-amzn-oidc-data(custom:groups)로 판정한 역할을 API로 받아 사용.
  return 'viewer'
}

export function canApprove(): boolean {
  return getRole() === 'approver'
}
