# =============================================================================
# infra/shared — 공유 기반 레이어 (레이어드 terraform 0번, 가장 먼저 apply)
# project-draft 4.6 · manual-infra 2번(state 부트스트랩)
# 입력 변수 = variables.tf / 출력 = outputs.tf
#
# 구역: [TF·BACKEND] [PROVIDER] [VPC] [NAT] [EKS] [ECR] [RDS] [IAM-OIDC] [IAM-ENGINE]
# =============================================================================


# =============================================================================
# [TF·BACKEND] terraform·provider 버전 + S3 원격 백엔드(네이티브 락)
# state 버킷 = cnapp-agentic-tfstate (manual-infra §2, 2026-07-01 부트스트랩 완료)
#    (backend 블록은 변수 불가 → 하드코딩. init 시 `--profile cnapp` 사용)
# =============================================================================
terraform {
  required_version = ">= 1.10" # S3 네이티브 락(use_lockfile) 지원

  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.95" } # NAT은 raw 리소스(모듈 충돌 회피)
    random = { source = "hashicorp/random", version = "~> 3.6" }
    tls    = { source = "hashicorp/tls", version = "~> 4.0" }
  }

  backend "s3" {
    bucket       = "cnapp-agentic-tfstate" # manual-infra §2 (2026-07-01 부트스트랩 생성)
    key          = "infra/shared/terraform.tfstate"
    region       = "ap-northeast-2"
    encrypt      = true
    use_lockfile = true
  }
}


# =============================================================================
# [PROVIDER]
# =============================================================================
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project
      Env       = var.env
      ManagedBy = "terraform"
      Layer     = "shared"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}


# =============================================================================
# [VPC] 2 AZ · NAT Gateway 끔(비용, 22번) · S3·DynamoDB Gateway Endpoint(무료)
# =============================================================================
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name = "${var.project}-shared"
  cidr = var.vpc_cidr
  azs  = var.azs

  public_subnets  = [for i in range(length(var.azs)) : cidrsubnet(var.vpc_cidr, 8, i)]
  private_subnets = [for i in range(length(var.azs)) : cidrsubnet(var.vpc_cidr, 8, i + 10)]

  enable_nat_gateway   = false # NAT Instance로 대체(아래 NAT 구역)
  enable_dns_hostnames = true
  enable_dns_support   = true

  public_subnet_tags  = { "kubernetes.io/role/elb" = 1 }          # EKS LB 디스커버리
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = 1 } # EKS 내부 LB
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc.private_route_table_ids
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${var.region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc.private_route_table_ids
}


# =============================================================================
# [NAT] raw NAT Instance(t4g.nano ~$3/월) — NAT Gateway($32) 대신(22번)
# private subnet 아웃바운드(노드 이미지 pull·EKS API·Bedrock·외부 API)용. S3/DDB는 위 Gateway Endpoint.
# ⚠️ apply 전: nat_ami_owner(fck-nat 퍼블리셔 계정) 검증 / 데모 외엔 중지·destroy
# =============================================================================
data "aws_ami" "fck_nat" {
  most_recent = true
  owners      = [var.nat_ami_owner]

  filter {
    name   = "name"
    values = ["fck-nat-al2023-*-arm64-ebs"]
  }
  filter {
    name   = "architecture"
    values = ["arm64"]
  }
}

resource "aws_security_group" "nat" {
  name        = "${var.project}-nat"
  description = "NAT instance - inbound from VPC, outbound to internet"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "from VPC private subnets"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "nat" {
  ami                         = data.aws_ami.fck_nat.id
  instance_type               = "t4g.nano"
  subnet_id                   = module.vpc.public_subnets[0]
  associate_public_ip_address = true
  source_dest_check           = false # NAT 핵심 — 자기 IP 아닌 트래픽 포워딩
  vpc_security_group_ids      = [aws_security_group.nat.id]

  # 하드닝(Checkov CKV_AWS_79) — IMDSv2 강제(v1 토큰리스 차단, SSRF 자격증명 탈취 표면 축소)
  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }
  # 하드닝(CKV_AWS_8) — 루트 EBS 암호화
  root_block_device {
    encrypted = true
  }

  tags = { Name = "${var.project}-nat" }
}

resource "aws_route" "private_nat" {
  count                  = length(module.vpc.private_route_table_ids)
  route_table_id         = module.vpc.private_route_table_ids[count.index]
  destination_cidr_block = "0.0.0.0/0"
  network_interface_id   = aws_instance.nat.primary_network_interface_id
}


# =============================================================================
# [EKS] spot t3.small · scale 0~2 · IRSA(D5) · API access entry
# D6(EKS+ArgoCD) · 22번(spot·scale-0)
# =============================================================================
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.24"

  cluster_name    = "${var.project}-shared"
  cluster_version = var.eks_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_public_access = true # 데모 편의. TODO: IP allowlist 또는 private 전환
  enable_irsa                    = true # 파드 키리스(D5)

  authentication_mode                      = "API_AND_CONFIG_MAP"
  enable_cluster_creator_admin_permissions = true

  access_entries = {
    for arn in var.cluster_admin_principal_arns : arn => {
      principal_arn = arn
      policy_associations = {
        admin = {
          policy_arn   = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = { type = "cluster" }
        }
      }
    }
  }

  eks_managed_node_groups = {
    default = {
      ami_type       = "AL2023_x86_64_STANDARD"
      instance_types = var.node_instance_types
      capacity_type  = "SPOT" # 비용(22번)
      min_size       = var.node_min
      max_size       = var.node_max
      desired_size   = var.node_desired

      # 하드닝(Checkov CKV_AWS_79) — IMDSv2 강제 + hop_limit=1(파드의 노드 IMDS 접근 차단 → IRSA 강제)
      metadata_options = {
        http_endpoint               = "enabled"
        http_tokens                 = "required"
        http_put_response_hop_limit = 1
      }
      # 하드닝(CKV_AWS_8) — 노드 EBS 암호화
      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size           = 20
            volume_type           = "gp3"
            encrypted             = true
            delete_on_termination = true
          }
        }
      }
    }
  }

  tags = { Layer = "shared" }
}


# =============================================================================
# [ECR] 워크로드 이미지 레지스트리(D6) · scan_on_push(D14)
# ※ 타깃 앱 '의도적' 결함(latest 태그·스캔 미설정 finding)은 infra/target에서 별도 구성
# =============================================================================
locals {
  ecr_repos = ["product", "order", "member", "console-backend"]
}

resource "aws_ecr_repository" "this" {
  for_each = toset(local.ecr_repos)

  name                 = "${var.project}/${each.value}"
  image_tag_mutability = "MUTABLE" # 데모. 공급망 강화 시 IMMUTABLE(D17)

  image_scanning_configuration {
    scan_on_push = true
  }

  force_delete = true # 데모 — destroy 편의
}


# =============================================================================
# [RDS] PostgreSQL t3.micro + pgvector(D9·24번) · private · Secrets Manager
# pgvector는 확장 — 앱/마이그레이션에서 CREATE EXTENSION IF NOT EXISTS vector;
# 비용(진우 결정): RDS Stop 7일 자동재기동 방지용 EventBridge Scheduler+Lambda는 TODO로 추가 예정
# =============================================================================
resource "random_password" "db" {
  length           = 24
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?" # RDS 미허용 문자 제외
}

resource "aws_secretsmanager_secret" "db" {
  name        = "${var.project}/rds/master"
  description = "RDS pgvector master credential (shared)"
  # ⚠️ 기본 30일 복구창 → destroy 시 이름이 30일 '삭제 예약'으로 점유되어 재-apply의 CreateSecret이
  #    'scheduled for deletion'으로 실패. apply→destroy→재apply 규율이 근간이라 즉시 삭제(0)로.
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db.result
    dbname   = var.db_name
  })
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.project}-db"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "rds" {
  name        = "${var.project}-rds"
  description = "RDS pgvector - 5432 from within VPC only"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "PostgreSQL from VPC (Lambda + EKS). TODO: narrow to source SG"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_parameter_group" "pg" {
  name   = "${var.project}-pg16"
  family = "postgres16"
}

resource "aws_db_instance" "pgvector" {
  identifier     = "${var.project}-pgvector"
  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  allocated_storage     = 20
  max_allocated_storage = 50
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result

  db_subnet_group_name    = aws_db_subnet_group.this.name
  vpc_security_group_ids  = [aws_security_group.rds.id]
  parameter_group_name    = aws_db_parameter_group.pg.name
  multi_az                = false
  publicly_accessible     = false
  backup_retention_period = 1

  skip_final_snapshot = true  # 데모
  deletion_protection = false # 데모
}


# =============================================================================
# [IAM-OIDC] GitHub OIDC → IAM Role(D4, 키 없음) · sub를 우리 레포로 제한
# =============================================================================
data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github.certificates[0].sha1_fingerprint]
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "github_ci" {
  name               = "${var.project}-github-ci"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
  # TODO: CI 최소권한 정책 attach(ECR push·EKS describe·해당 infra apply). 17번 최소권한으로 좁히기
}


# =============================================================================
# [IAM-ENGINE] 엔진 정책 2종 — 계약과 동기화. 실행 역할(Lambda)은 infra/engine에서 attach
#  (1) Evidence read-only = contracts/evidence-allowlist.json과 1:1 (변경 API 없음, 17번)
#  (2) Bedrock invoke
# =============================================================================
data "aws_iam_policy_document" "evidence_readonly" {
  statement {
    sid    = "EvidenceReadOnly"
    effect = "Allow"
    actions = [
      "s3:GetBucketPolicy",
      "s3:GetBucketAcl",
      "s3:GetPublicAccessBlock",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:SimulatePrincipalPolicy",
      "macie2:GetFindings",
      "ec2:DescribeSecurityGroups",
      "accessanalyzer:ListFindings"
    ]
    resources = ["*"] # 전부 read-only라 * 가능. TODO: 가능한 액션은 리소스 좁히기
  }
}

resource "aws_iam_policy" "evidence_readonly" {
  name        = "${var.project}-evidence-readonly"
  description = "Evidence 에이전트 read-only allowlist (contracts/evidence-allowlist.json)"
  policy      = data.aws_iam_policy_document.evidence_readonly.json
}

data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid       = "BedrockInvoke"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = ["*"] # TODO: 서울 가용 모델 ARN으로 좁히기(haiku·sonnet·titan). 모델 액세스 콘솔 활성화 선행
  }
}

resource "aws_iam_policy" "bedrock_invoke" {
  name        = "${var.project}-bedrock-invoke"
  description = "에이전트 Bedrock InvokeModel"
  policy      = data.aws_iam_policy_document.bedrock_invoke.json
}
