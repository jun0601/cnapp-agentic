variable "region" {
  description = "AWS 리전"
  type        = string
  default     = "ap-northeast-2"
}

variable "profile" {
  description = "AWS CLI 프로파일(로컬 테스트용). CI/OIDC면 null."
  type        = string
  default     = null
}

variable "bucket_prefix" {
  description = "슬라이스 버킷 이름 접두사(뒤에 랜덤 suffix 붙어 전역 유일)"
  type        = string
  default     = "cnapp-slice-member-pii"
}

variable "enable_public_policy" {
  description = "공개 읽기 버킷 정책 부여 여부. 계정 레벨 BPA가 켜져 있으면 apply 거부될 수 있음 → false면 PAB-off 신호만으로 데모."
  type        = bool
  default     = true
}
