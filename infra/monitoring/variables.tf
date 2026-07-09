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
  description = "이 레이어가 만드는 CloudWatch 로그(Teams notifier Lambda·CloudTrail 연동 로그그룹) 보존 — 다른 레이어와 통일"
  type        = number
  default     = 14
}

# --- Grafana IRSA(K8s ServiceAccount) — gitops/monitoring/values.yaml과 반드시 일치 ---
variable "grafana_namespace" {
  description = "Grafana가 배포될 K8s 네임스페이스(gitops/monitoring/values.yaml과 일치)"
  type        = string
  default     = "monitoring"
}

variable "grafana_service_account" {
  description = "kube-prometheus-stack 기본 Grafana SA 이름(release=kube-prometheus-stack 기준, <release>-grafana)"
  type        = string
  default     = "kube-prometheus-stack-grafana"
}

# --- Bedrock 비용 위젯(metric math) 단가 — README §2③.2. AWS 가격은 수시 변동되므로
#     apply 직전 Bedrock 가격 페이지에서 재확인 후 -var로 덮어쓰는 걸 권장(하드코딩 최소화 목적으로 변수화).
variable "bedrock_haiku_price_in_per_1k" {
  description = "Claude Haiku 4.5 입력 토큰 단가(USD/1K) — 2026-07 대략치, apply 전 재확인"
  type        = number
  default     = 0.001
}

variable "bedrock_haiku_price_out_per_1k" {
  description = "Claude Haiku 4.5 출력 토큰 단가(USD/1K) — 2026-07 대략치, apply 전 재확인"
  type        = number
  default     = 0.005
}

# Sonnet은 아직 mock(Reasoning/Hypothesis/RAG 실전환 전) — 실사용 전환 시 이 값도 재확인해서 쓰면 됨.
variable "bedrock_sonnet_price_in_per_1k" {
  description = "Claude Sonnet 입력 토큰 단가(USD/1K) — Reasoning/RAG 실전환 시 사용, apply 전 재확인"
  type        = number
  default     = 0.003
}

variable "bedrock_sonnet_price_out_per_1k" {
  description = "Claude Sonnet 출력 토큰 단가(USD/1K) — Reasoning/RAG 실전환 시 사용, apply 전 재확인"
  type        = number
  default     = 0.015
}

variable "bedrock_hourly_cost_alarm_usd" {
  description = "Bedrock 시간당 추정비용 알람 임계값(USD) — 정밀 예산 통제가 아니라 무한루프·비정상 다량 호출을 조기에 잡는 안전망. 데모 규모 기준 여유값(가격 변수 재확인 시 함께 점검)"
  type        = number
  default     = 1.0
}

variable "rds_connections_alarm_threshold" {
  description = "RDS DatabaseConnections 알람 임계치(db.t3.micro 기준 여유값)"
  type        = number
  default     = 80
}

# --- Grafana Ingress가 만드는 ALB — Kubernetes(ALB Controller)가 발급하므로 Terraform이
#     모름. EKS/Ingress 재생성 시 `kubectl get ingress grafana -n monitoring`으로 새
#     DNS 이름 확인 후 -var로 갱신(또는 이 default 값 갱신) 필요. ---
variable "grafana_alb_dns_name" {
  description = "Grafana Ingress ALB의 DNS 이름(kubectl get ingress grafana -n monitoring의 ADDRESS 컬럼)"
  type        = string
  default     = "k8s-monitori-grafana-9f9e2719d7-293394550.ap-northeast-2.elb.amazonaws.com"
}

variable "grafana_alb_zone_id" {
  description = "위 ALB의 canonical hosted zone id(aws elbv2 describe-load-balancers) — 리전별 ALB 고정값이라 서울 리전이면 거의 안 바뀜"
  type        = string
  default     = "ZWKZPGTI48KDX"
}
