# =============================================================================
# infra/target — 취약 워크로드의 '의도적 결함' IaC (레이어드: shared 다음)
# ⚠️ 이 레이어는 '일부러 취약'하다. 격리 환경·데모 기간에만 apply, 끝나면 destroy.
# 결함 토글 = var.enable_*  (개별 토글 — target-app-design §7 권장: 조합 테스트 용이)
#
# 구역: [BACKEND] [PROVIDER] [SHARED refs] [S3 f6/f7] [SG f3] [IRSA order f4 / member clean]
# =============================================================================

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.95" }
  }
  backend "s3" {
    bucket       = "cnapp-agentic-tfstate" # manual-infra §2
    key          = "infra/target/terraform.tfstate"
    region       = "ap-northeast-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project   = var.project
      Env       = var.env
      Layer     = "target"
      ManagedBy = "terraform"
      Warning   = "intentionally-vulnerable-demo"
    }
  }
}

data "aws_caller_identity" "current" {}

# infra/shared 출력 참조(레이어드) — VPC·OIDC provider 등
data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket = "cnapp-agentic-tfstate"
    key    = "infra/shared/terraform.tfstate"
    region = var.region
  }
}

# =============================================================================
# [S3] member 회원 PII 버킷 (f6 공개=INTERNAL-S3-PUBLIC-001 · f7 PII=INTERNAL-DATA-PII-EXPOSED-001, seeder 적재)
# =============================================================================
resource "aws_s3_bucket" "member_pii" {
  # S3 버킷 이름은 전 세계 유일해야 함 — "member-pii-prod"만 쓰면 다른 계정이 이미 선점했을 수
  # 있어 apply가 실패할 수 있다(front-${account_id}·audit-${account_id}과 동일 컨벤션으로 계정ID
  # 접미사 추가, 2026-07-03 apply 전 검증에서 발견). 계정ID는 apply 후에만 알 수 있어 apps/target
  # /member/k8s/deployment.yaml의 MEMBER_PII_BUCKET env(placeholder)도 IRSA role-arn과 동일하게
  # apply 후 실제 값으로 1회 수동 치환 필요.
  bucket        = "${var.member_pii_bucket}-${data.aws_caller_identity.current.account_id}"
  force_destroy = true # 데모 — destroy 편의
}

# f6 결함 토글: enable_s3_public=true면 public access block을 '풀어' 공개 허용
resource "aws_s3_bucket_public_access_block" "member_pii" {
  bucket                  = aws_s3_bucket.member_pii.id
  block_public_acls       = !var.enable_s3_public
  block_public_policy     = !var.enable_s3_public
  ignore_public_acls      = !var.enable_s3_public
  restrict_public_buckets = !var.enable_s3_public
}

# f6: 공개 read 정책(토글 시에만). ❌ 의도적 결함 — 데모 전용.
data "aws_iam_policy_document" "public_read" {
  count = var.enable_s3_public ? 1 : 0
  statement {
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.member_pii.arn}/*"]
  }
}

resource "aws_s3_bucket_policy" "public_read" {
  count      = var.enable_s3_public ? 1 : 0
  bucket     = aws_s3_bucket.member_pii.id
  policy     = data.aws_iam_policy_document.public_read[0].json
  depends_on = [aws_s3_bucket_public_access_block.member_pii]
}

# =============================================================================
# [SG] f3 열린 보안그룹(INTERNAL-SG-OPEN-INGRESS-001, 0.0.0.0/0 인바운드) — 토글
# =============================================================================
resource "aws_security_group" "open_ingress" {
  count       = var.enable_open_sg ? 1 : 0
  name        = "${var.project}-target-open"
  description = "INTENTIONAL DEFECT f3 - open ingress (demo only)"
  vpc_id      = data.terraform_remote_state.shared.outputs.vpc_id

  ingress {
    description = "f3 defect - open to internet"
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # ❌ 의도적 결함
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# =============================================================================
# [IRSA] order 과도권한(f4=INTERNAL-IAM-OVERPRIV-001) vs member 최소권한(clean)
# OIDC provider는 infra/shared 출력에서 참조
# =============================================================================
locals {
  oidc_provider_arn = data.terraform_remote_state.shared.outputs.eks_oidc_provider_arn
  oidc_provider_url = data.terraform_remote_state.shared.outputs.eks_oidc_provider
}

# IRSA 신뢰정책 — 역할별로 :sub를 해당 ServiceAccount에 고정(:aud + :sub).
# :sub 없이 :aud만 걸면 클러스터 내 어떤 SA든 assume 가능 → member '최소권한 대조군'이 무의미.
data "aws_iam_policy_document" "member_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:shop:member"]
    }
  }
}

data "aws_iam_policy_document" "order_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:shop:order"]
    }
  }
}

# member IRSA — 최소권한(자기 버킷 Put/Head만). '깨끗한' 대조군(권한도 신뢰관계도 최소).
resource "aws_iam_role" "member_irsa" {
  name               = "${var.project}-target-member-irsa"
  assume_role_policy = data.aws_iam_policy_document.member_assume.json
}

resource "aws_iam_role_policy" "member_irsa" {
  name = "member-pii-put"
  role = aws_iam_role.member_irsa.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        # HeadObject(seeder의 존재 확인)는 IAM에 별도 액션이 없고 s3:GetObject로 인가된다.
        # (2026-07-07 실측: s3:HeadObject는 무효 액션 → head_object가 403 → seeder 실패.)
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = "${aws_s3_bucket.member_pii.arn}/*"
      },
      {
        Effect = "Allow"
        # ListBucket 없이는 '없는 객체'의 HeadObject를 S3가 404가 아닌 403으로 응답(존재 은닉)
        # → seeder가 404만 '없음'으로 처리하므로 403에서 재던져 실패했음(2026-07-07 실측).
        # 버킷 스코프 List만 허용(객체 접근은 위 문 그대로 최소).
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.member_pii.arn
      },
    ]
  })
}

# order IRSA — f4 결함: 과도권한(s3:*). 토글 시 wildcard, 아니면 최소.
# (신뢰관계는 order SA로 정상 고정 — 결함은 '권한 범위'지 신뢰관계가 아님)
resource "aws_iam_role" "order_irsa" {
  name               = "${var.project}-target-order-irsa"
  assume_role_policy = data.aws_iam_policy_document.order_assume.json
}

resource "aws_iam_role_policy" "order_irsa" {
  name = "order-s3"
  role = aws_iam_role.order_irsa.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      # ❌ f4 결함: enable_overpriv_irsa=true면 s3:* on * (과도권한)
      Action   = var.enable_overpriv_irsa ? ["s3:*"] : ["s3:GetObject"]
      Resource = var.enable_overpriv_irsa ? ["*"] : ["${aws_s3_bucket.member_pii.arn}/*"]
    }]
  })
}
