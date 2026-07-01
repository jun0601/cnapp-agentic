// ── 계약 타입 (contracts/*.schema.json 미러) ────────────────────────────────
// SSOT = contracts/*.schema.json. 이 파일은 그 손번역이며, `npm run gen:types`로
// scripts/gen-types.mjs가 재생성한다(json-schema-to-typescript). drift 시 재생성.

export type Cloud = 'aws' | 'azure'
export type Pillar = 'cspm' | 'ciem' | 'vuln' | 'kspm' | 'data' | 'attack_path'
export type ResourceType =
  | 's3_bucket'
  | 'iam_role'
  | 'eks_pod'
  | 'security_group'
  | 'secret_plaintext'
  | 'app_registration'
  | 'service_principal'
  | 'ecr_repo'
  | 'other'
export type FindingStatus = 'open' | 'remediated' | 'suppressed'
export type AiStatus = 'pending' | 'done' | 'failed'

/** severity_id 내부 컨벤션: 1=Critical … 5=Info (낮을수록 심각, 실제 OCSF와 반대) */
export type SeverityId = 1 | 2 | 3 | 4 | 5

/** 계약① — OCSF-lite Finding */
export interface Finding {
  finding_id: string
  cloud: Cloud
  resource_id: string
  resource_type: ResourceType
  pillar: Pillar
  control_id: string
  title: string
  severity_id: SeverityId
  status: FindingStatus
  sources: string[]
  dedup_key: string
  priority_score?: number | null
  attack_path_id?: string | null
  ai_status: AiStatus
  first_seen: string
  last_seen: string
  raw_ref?: string | null
}

/** 계약③ — Attack-path Graph */
export type EdgeType = 'lateral_move' | 'credential_theft' | 'data_exfil' | 'identity_takeover'

export interface AttackPathNode {
  id: string
  cloud: Cloud
  resource_id: string
  label: string
  pillar: Pillar
}

export interface AttackPathEdge {
  from: string
  to: string
  type: EdgeType
  cross_cloud?: boolean
  label?: string
}

export interface AttackPath {
  attack_path_id: string
  severity_id: SeverityId
  nodes: AttackPathNode[]
  edges: AttackPathEdge[]
  narrative_text: string
}

/** 계약⑦ — Engine Case (agent handoff) */
export interface EvidenceItem {
  tool: string
  resource_id: string
  result_summary: string
  raw?: Record<string, unknown>
  ts: string
}

export interface Case {
  case_id: string
  finding: { finding_ids: string[] } | Finding
  stage: 'triage' | 'hypothesis' | 'evidence' | 'reasoning'
  triage?: { priority_score?: number; escalate?: boolean; reason?: string }
  hypotheses?: string[]
  evidence?: EvidenceItem[]
  evidence_meta?: {
    tool_calls_count?: number
    confidence_score?: number
    verdict?: 'confirmed' | 'refuted' | 'inconclusive'
  }
  reasoning?: {
    verdict?: string
    confidence_score?: number
    narrative?: string
    rag_refs?: string[]
  }
  model_trace?: { stage?: string; model?: string; tokens?: number }[]
}

/** UC1 — finding당 AI 설명(§5 finding_explanations). 엔진 미구현 단계선 파생/placeholder. */
export interface FindingExplanation {
  finding_id: string
  summary: string
  why: string
  how: string
  ai_status: AiStatus
  case_id?: string | null
}

/** GET /findings/:id 응답 = finding + explanation(finding당) + case(조인, 없으면 null) */
export interface FindingDetail {
  finding: Finding
  explanation: FindingExplanation | null
  case: Case | null
}

/** GET /scores */
export interface Scores {
  aws: { secure_score: number; label: string }
  azure: { secure_score: number; label: string }
}
