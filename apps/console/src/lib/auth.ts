// Cognito 토큰 자리(§7 RBAC — viewer/approver). 목업 단계선 placeholder.
// 실연동: Entra→Cognito→ALB(authenticate-oidc) 토큰의 그룹 클레임으로 역할 판정.

export type Role = 'viewer' | 'approver'

export function getRole(): Role {
  // TODO: Cognito id_token의 cognito:groups 클레임에서 파생.
  return 'viewer'
}

export function canApprove(): boolean {
  return getRole() === 'approver'
}
