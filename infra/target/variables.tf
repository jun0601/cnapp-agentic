variable "project" {
  type    = string
  default = "cnapp-agentic"
}

variable "env" {
  type    = string
  default = "demo"
}

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "member_pii_bucket" {
  type        = string
  default     = "member-pii-prod"
  description = "회원 합성 PII 버킷(member seeder가 적재, Macie 대상)"
}

# ── 결함 토글(개별) — target-app-design §7 권장. 기본 off(안전), 데모 시 켠다. ──
variable "enable_s3_public" {
  type        = bool
  default     = false
  description = "f6: member PII 버킷 공개 노출"
}

variable "enable_open_sg" {
  type        = bool
  default     = false
  description = "f3: 0.0.0.0/0 인바운드 열린 SG"
}

variable "enable_overpriv_irsa" {
  type        = bool
  default     = false
  description = "f4: order IRSA 과도권한(s3:* on *)"
}
