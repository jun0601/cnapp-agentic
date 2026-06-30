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
variable "eks_version" {
  type    = string
  default = "1.30"
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
  description = "pgvector 지원(>=15.2). PG16 사용"
  type        = string
  default     = "16.4"
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
  description = "EKS cluster admin으로 등록할 IAM 사용자/역할 ARN (jh_lee·jw_kim). apply 전 실제 ARN 채우기."
  type        = list(string)
  default     = [] # TODO: ["arn:aws:iam::<acct>:user/jh_lee","arn:aws:iam::<acct>:user/jw_kim"]
}
