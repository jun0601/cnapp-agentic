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

// AI·시스템 관측(/system) — 모델 구성·RAG 지식베이스(pgvector)·Bedrock 사용량(24h)·데이터 현황.
export interface SystemInfo {
  live: boolean
  models: { chat: string; embed: string; engine: string }
  rag: { chunks: number; controls: number; dim: number; index: string }
  bedrock: { invocations24h: number; inputTokens24h: number; outputTokens24h: number } // -1 = 집계 불가
  data: { findingsOpen: number; findingsTotal: number; attackPaths: number; cases: number }
}
export function useSystem() {
  return useQuery({
    queryKey: ['system'],
    queryFn: () => apiGet<SystemInfo>('/system'),
    refetchInterval: 60_000, // Bedrock 사용량은 분 단위 갱신이면 충분
  })
}

// AI 재조사(라이브 트리거) — orchestrator Lambda 비동기 invoke(백엔드 202). 조사(트리아지→
// Evidence 실 Bedrock tool-use→Reasoning)는 수십 초~분 단위라 지연 invalidate로 결과를 끌어온다.
export function useReanalyze(id: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiPost<{ accepted: boolean; mode?: string }>(`/findings/${id}/reanalyze`),
    onSuccess: () => {
      for (const delay of [30_000, 60_000, 120_000]) {
        setTimeout(() => {
          void qc.invalidateQueries({ queryKey: ['finding', id] })
          void qc.invalidateQueries({ queryKey: ['findings'] })
        }, delay)
      }
    },
  })
}

// 조치 승인/거부(UC4, HITL) — approver만. 승인 시 백엔드가 remediation SFn StartExecution.
// ⚠️ 조치는 비동기 체인: 승인 → SFn → remediation Lambda(finding=remediated) → correlation 재계산(경로 소멸).
// HTTP 응답은 StartExecution만이라 즉시 끝나지만, 실제 효과(점수↑·경로↓)는 수초~수십초 뒤 RDS에 반영된다.
// 그래서 findings뿐 아니라 scores·attack-paths까지, 즉시 + 지연(4·10·20·40초)으로 반복 무효화해
// "승인 클릭 → 대시보드가 스스로 점수 오르고 경로 사라짐"이 데모에서 자동으로 보이게 한다.
export function useRemediationDecision() {
  const qc = useQueryClient()
  const refreshDemoState = () => {
    void qc.invalidateQueries({ queryKey: ['findings'] })
    void qc.invalidateQueries({ queryKey: ['scores'] })
    void qc.invalidateQueries({ queryKey: ['attack-paths'] })
    void qc.invalidateQueries({ queryKey: ['audit'] })
  }
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'approve' | 'reject' }) =>
      apiPost<{ ok: boolean; execution_arn?: string }>(`/remediations/${id}/${action}`),
    onSuccess: () => {
      refreshDemoState() // 즉시(거부·빠른 반영분)
      for (const delay of [4_000, 10_000, 20_000, 40_000]) setTimeout(refreshDemoState, delay)
    },
  })
}
