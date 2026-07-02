# infra/slice — 엔진 실 tool-use vertical slice 전용 (최소 비용)
#
# 목적: 공개 S3 버킷 1개 + 가짜 PII 객체 1개를 만들어, RealToolExecutor(engine/core/tools.py)가
#       실제 read-only API(s3:GetBucketPolicy·GetPublicAccessBlock)로 조사하게 한다.
#       "LLM이 스스로 진짜 API를 호출해 판정" 컨셉을 최소 크레딧으로 증명하는 표적.
#
# ⚠️ 규율: apply는 준형과 함께 · 테스트 후 즉시 `terraform destroy` · Macie 안 켬(비용).
#          infra/shared(EKS·RDS·NAT)와 무관한 독립 스택 — 이 폴더만 apply하면 됨.
#          모든 PII는 faker 합성값(실제 개인정보 아님). 격리 데모 전제.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.0" }
  }
}

provider "aws" {
  region  = var.region
  profile = var.profile
}

resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  bucket_name = "${var.bucket_prefix}-${random_id.suffix.hex}"
}

resource "aws_s3_bucket" "pii" {
  bucket        = local.bucket_name
  force_destroy = true # destroy 시 객체까지 제거(슬라이스 휘발성)
  tags = {
    project   = "cnapp-agentic"
    purpose   = "vertical-slice"
    ephemeral = "true"
  }
}

# 결함: public access block 전부 해제 → GetPublicAccessBlock가 '차단 없음'으로 관측
resource "aws_s3_bucket_public_access_block" "pii" {
  bucket                  = aws_s3_bucket.pii.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

# 결함: 공개 읽기 정책 → GetBucketPolicy가 Principal:"*"로 관측
# ⚠️ 계정 레벨 S3 Block Public Access가 켜져 있으면 이 정책 apply가 거부될 수 있음
#    (apply 때 준형과 함께 확인 — 필요 시 enable_public_policy=false로 두고 PAB 신호만으로 데모).
resource "aws_s3_bucket_policy" "pii_public" {
  count      = var.enable_public_policy ? 1 : 0
  bucket     = aws_s3_bucket.pii.id
  depends_on = [aws_s3_bucket_public_access_block.pii]
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "PublicRead"
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.pii.arn}/*"
    }]
  })
}

# 가짜 PII 객체(faker 형식 합성값 — 실제 개인정보 아님). 실 골든에선 Macie 미끼이나 slice엔 Macie 안 켬.
resource "aws_s3_object" "fake_pii" {
  bucket = aws_s3_bucket.pii.id
  key    = "members/fake-pii.json"
  content = jsonencode([
    { name = "홍길동", rrn = "900101-1234567", email = "fake1@example.com" },
    { name = "김철수", rrn = "880202-2345678", email = "fake2@example.com" }
  ])
  content_type = "application/json"
}
