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

# --- Karpenter ---
variable "karpenter_chart_version" {
  description = "Karpenter helm 차트(=앱) 버전. ⚠️ '차트가 존재하는가'가 아니라 'K8s 버전과 호환되는가'를 봐야 함 — 1.1.1은 존재하지만 K8s 1.34에서 컨트롤러가 시작 즉시 panic('karpenter version is not compatible with K8s version 1.34', 2026-07-03 실검증). apply 전 `helm show chart oci://public.ecr.aws/karpenter/karpenter`로 최신 확인 + Karpenter 호환성 매트릭스에서 클러스터 K8s 버전 지원 확인."
  type        = string
  default     = "1.13.0" # 2026-07-03 최신(appVersion 1.13.0) — K8s 1.34 호환 확인
}
