// TanStack Query 훅 — 30~60초 폴링(§6.2)·캐싱·수동 새로고침(invalidate)이 선언적.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from './client'
import type { Finding, FindingDetail, AttackPath, Scores } from './types'
import type { AuditEvent, ComplianceReport } from './view-types'

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

export function useAudit() {
  return useQuery({
    queryKey: ['audit'],
    queryFn: () => apiGet<AuditEvent[]>('/audit'),
  })
}

export function useCompliance() {
  return useQuery({
    queryKey: ['compliance'],
    queryFn: () => apiGet<ComplianceReport>('/compliance'),
  })
}

// AI 어시스턴트(RAG) — 자연어 질의 → Titan 임베딩 → pgvector 검색 → Bedrock(Haiku) 답변.
// 백엔드 POST /chat({q}) → {answer, refs[]}. 실 지식베이스(rag_chunks) 근거로 답변.
export interface ChatRef {
  control: string
  snippet: string
}
export function useChat() {
  return useMutation({
    mutationFn: (q: string) => apiPost<{ answer: string; refs: ChatRef[] }>('/chat', { q }),
  })
}

// 조치 승인/거부(UC4, HITL) — approver만. 승인 시 백엔드가 remediation SFn StartExecution.
// 성공하면 findings 캐시를 무효화(승인된 finding은 remediated로 소멸 → 목록 갱신).
export function useRemediationDecision() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'approve' | 'reject' }) =>
      apiPost<{ ok: boolean; execution_arn?: string }>(`/remediations/${id}/${action}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['findings'] })
      void qc.invalidateQueries({ queryKey: ['audit'] })
    },
  })
}
