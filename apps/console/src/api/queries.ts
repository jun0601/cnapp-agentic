// TanStack Query 훅 — 30~60초 폴링(§6.2)·캐싱·수동 새로고침(invalidate)이 선언적.
import { useQuery } from '@tanstack/react-query'
import { apiGet } from './client'
import type { Finding, FindingDetail, AttackPath, Scores } from './types'

export interface FindingsFilter {
  cloud?: string
  pillar?: string
  status?: string
  sort?: string
  [key: string]: string | undefined
}

const POLL_MS = 45_000 // §6.2 — 30~60초 폴링

export function useFindings(filter: FindingsFilter = {}) {
  return useQuery({
    queryKey: ['findings', filter],
    queryFn: () => apiGet<Finding[]>('/findings', filter),
    refetchInterval: POLL_MS,
  })
}

export function useFinding(id: string | undefined) {
  return useQuery({
    queryKey: ['finding', id],
    queryFn: () => apiGet<FindingDetail>(`/findings/${id}`),
    enabled: !!id,
  })
}

export function useAttackPaths() {
  return useQuery({
    queryKey: ['attack-paths'],
    queryFn: () => apiGet<AttackPath[]>('/attack-paths'),
    refetchInterval: POLL_MS,
  })
}

export function useAttackPath(id: string | undefined) {
  return useQuery({
    queryKey: ['attack-path', id],
    queryFn: () => apiGet<AttackPath>(`/attack-paths/${id}`),
    enabled: !!id,
  })
}

export function useScores() {
  return useQuery({
    queryKey: ['scores'],
    queryFn: () => apiGet<Scores>('/scores'),
    refetchInterval: POLL_MS,
  })
}
