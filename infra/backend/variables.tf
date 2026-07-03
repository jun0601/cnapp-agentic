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
  description = "Lambda 로그 보존(비용 — 데모는 짧게)"
  type        = number
  default     = 14
}
