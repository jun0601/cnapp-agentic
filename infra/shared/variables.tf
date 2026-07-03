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

# --- 네트워크 ---
variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "azs" {
  description = "2 AZ면 충분(데모·비용)"
  type        = list(string)
  default     = ["ap-northeast-2a", "ap-northeast-2c"]
}

# --- CI 키리스(D4) ---
variable "github_repo" {
  description = "GitHub OIDC sub 제한용 owner/repo"
  type        = string
  default     = "jun0601/cnapp-agentic"
}

# --- NAT instance ---
variable "nat_ami_owner" {
  description = "fck-nat 공개 AMI 퍼블리셔 계정 ID. apply 전 검증 필수(틀리면 AMI 조회 실패)."
  type        = string
  default     = "568608671756" # TODO: fck-nat 공식 계정 ID 검증
}

# --- EKS ---
# ⚠️ 반드시 STANDARD_SUPPORT 버전 사용 — EXTENDED_SUPPORT(1.32 이하, 2026-07 기준)는
#    컨트롤플레인이 $0.10/h → $0.60/h(6배)로 과금됨. 표준지원=1.33~1.36(2026-07-02 aws eks describe-cluster-versions 확인).
#    1.34 표준지원 종료 2026-12-02 → 데모 여유. apply 전 재확인 권장.
variable "eks_version" {
  type    = string
  default = "1.34"
}

variable "node_instance_types" {
  description = "작은 노드(비용) — 22번"
  type        = list(string)
  default     = ["t3.small"]
}

variable "node_min" {
  type    = number
  default = 0 # 비데모 시 scale-to-0
}

variable "node_max" {
  type    = number
  default = 2
}

variable "node_desired" {
  type    = number
  default = 2
}

# --- RDS pgvector ---
variable "db_instance_class" {
  description = "RDS PostgreSQL t3.micro — 24번 확정"
  type        = string
  default     = "db.t3.micro"
}

variable "db_engine_version" {
  # ⚠️ 16.4는 서울에서 이미 제거됨(apply 시 "Cannot find version 16.4"). 2026-07-02 가용=16.9~16.14(pgvector OK).
  # engine_version 검증은 plan이 아니라 apply 때 발생 → plan 클린이어도 apply 실패하던 버그. apply 전 재확인 권장.
  description = "pgvector 지원 PG16 (family=postgres16). 가용 minor는 apply 전 확인."
  type        = string
  default     = "16.9"
}

variable "db_name" {
  type    = string
  default = "cnapp"
}

variable "db_username" {
  type    = string
  default = "cnapp_admin"
}

# --- 운영자 접근 ---
variable "cluster_admin_principal_arns" {
  description = "EKS cluster admin으로 추가 등록할 IAM 사용자/역할 ARN. jh_lee(생성자)는 enable_cluster_creator_admin_permissions로 자동 admin이라 여기 안 넣음(중복 access entry 충돌). 진우(jw_kim)는 생성자가 아니라 여기 명시해야 kubectl 접근 가능(2026-07-03 진우 요청)."
  type        = list(string)
  default     = ["arn:aws:iam::066107819776:user/jw_kim"]
}

# --- Karpenter(karpenter.tf) ---
variable "karpenter_chart_version" {
  description = "Karpenter helm 차트(=앱) 버전. Karpenter 1.x. ⚠️ apply 전 최신 안정 1.x 확인(잘못되면 helm이 차트 못 찾아 실패). oci://public.ecr.aws/karpenter/karpenter."
  type        = string
  default     = "1.1.1"
}
