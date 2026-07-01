// 콘솔-로컬 뷰 타입 — audit(UC4)·compliance(UC5)는 아직 contracts로 졸업 안 함.
// 실데이터 붙일 때 contracts/*.schema.json으로 승격 예정(현재는 목업 전용).

export type AuditAction = 'approve' | 'reject' | 'verdict' | 'scan' | 'view' | 'login'

export interface AuditEvent {
  id: string
  ts: string
  actor: string // 이메일 또는 시스템("engine"/"scanner")
  role: 'viewer' | 'approver' | 'system'
  action: AuditAction
  target: string // resource_id · finding_id · case_id 등
  result: string
}

export type ComplianceStatus = 'pass' | 'fail' | 'na'

export interface ComplianceControl {
  code: string // 프레임워크 항목 코드 (예: ISMS-P 2.6.1)
  title: string
  status: ComplianceStatus
  mapped_control?: string // 우리 INTERNAL control_id
  findings: number // 관련 open finding 수
}

export interface ComplianceDomain {
  code: string
  name: string
  controls: ComplianceControl[]
}

export interface ComplianceReport {
  framework: string
  generated_at: string
  score: number // 0~100 (pass / (pass+fail))
  domains: ComplianceDomain[]
}
