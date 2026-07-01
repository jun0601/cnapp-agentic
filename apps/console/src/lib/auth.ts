// 역할(§7 RBAC — viewer/approver).
//
// 실데이터(진우 확정): Entra SAML attr → Cognito custom:groups → ALB(authenticate-cognito)가
// x-amzn-oidc-data JWT로 실어 보냄 → 역할 판정은 console-backend(Lambda)에서 수행.
// 프론트는 AWS를 직접 호출하지 않으므로(Identity Pool 미사용) 백엔드가 내려준 역할을 표시만 한다.
//
// 목업/개발 단계: 역할을 런타임 전환 가능하게 한다(진우 제안 = VITE_MOCK_ROLE).
//   우선순위 = localStorage(헤더 스위처) > VITE_MOCK_ROLE(빌드 env) > 'viewer'(기본).
import { useSyncExternalStore } from 'react'

export type Role = 'viewer' | 'approver'

const KEY = 'cnapp:mockRole'
const listeners = new Set<() => void>()

function isRole(v: unknown): v is Role {
  return v === 'viewer' || v === 'approver'
}

function envRole(): Role {
  return import.meta.env.VITE_MOCK_ROLE === 'approver' ? 'approver' : 'viewer'
}

export function getRole(): Role {
  // TODO(실데이터): 백엔드가 x-amzn-oidc-data(custom:groups)로 판정한 역할을 API로 받아 대체.
  if (typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem(KEY)
    if (isRole(stored)) return stored
  }
  return envRole()
}

export function setRole(r: Role): void {
  localStorage.setItem(KEY, r)
  listeners.forEach((l) => l())
}

export function canApprove(): boolean {
  return getRole() === 'approver'
}

function subscribe(l: () => void): () => void {
  listeners.add(l)
  return () => listeners.delete(l)
}

/** 역할 구독 훅 — 헤더 스위처로 바꾸면 관련 컴포넌트가 즉시 리렌더된다. */
export function useRole(): Role {
  return useSyncExternalStore(subscribe, getRole, getRole)
}

/** 개발 환경(목업)에서만 역할 스위처 노출 */
export const IS_MOCK = import.meta.env.VITE_USE_MOCK !== 'false'
