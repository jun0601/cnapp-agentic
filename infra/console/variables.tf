variable "region" {
  description = "단일 리전(서울) — D2"
  type        = string
  default     = "ap-northeast-2"
}

variable "project" {
  type    = string
  default = "cnapp-agentic"
}

variable "env" {
  type    = string
  default = "demo"
}

variable "tfstate_bucket" {
  description = "레이어드 remote_state 버킷(manual-infra §2)"
  type        = string
  default     = "cnapp-agentic-tfstate"
}

variable "log_retention_days" {
  type    = number
  default = 14
}

# --- Cognito / SSO ---
variable "cognito_domain_prefix" {
  description = "Cognito Hosted UI 도메인 프리픽스(전역 유일). apply 전 유일성 확인."
  type        = string
  default     = "cnapp-agentic-demo"
}

variable "saml_metadata_url" {
  description = "Entra ID(IdP) SAML 메타데이터 URL — 진우 Entra App Reg(SSO)에서 발급(manual-infra §3). 미정 시 빈값(IdP 없이 apply, SSO는 나중)."
  type        = string
  default     = ""
}

# --- ALB HTTPS(authenticate-cognito는 HTTPS 필수) ---
variable "acm_certificate_arn" {
  description = "ALB 443 리스너용 ACM 인증서 ARN. authenticate-cognito는 HTTPS 필수 → 도메인+ACM 선행. 미정 시 빈값(apply 전 채우기)."
  type        = string
  default     = ""
}

# --- 조치(HITL) 연동 ---
variable "remediation_state_machine_arn" {
  description = "infra/engine output remediation_state_machine_arn. approver 승인 시 console-backend가 StartExecution. 미정 시 빈값(권한 전체 허용 안 함)."
  type        = string
  default     = ""
}

# --- console-backend 동작 모드 ---
variable "use_mock" {
  description = "true=계약 mock JSON 서빙 / false=pgvector 실쿼리(PG_DSN 필요)"
  type        = string
  default     = "false" # 실배포는 실데이터. 로컬 스모크만 mock.
}
