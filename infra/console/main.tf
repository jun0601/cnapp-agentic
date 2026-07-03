# =============================================================================
# infra/console — 관제 앱 (레이어드: shared 다음 · engine 참조)
# console-app-design §4·§7·§12 · project-draft §10(SSO)·§13(정적 호스팅)
#
# 구성:
#   [프론트]  S3(정적) + CloudFront(OAC)                        ← apps/console 빌드
#   [인증]    Cognito User Pool ← Entra(SAML IdP) · custom:groups → viewer/approver
#   [API]     ALB(authenticate-cognito, HTTPS) → Lambda(console-backend)  ← 타깃 EKS와 분리
#   [데이터]  console-backend Lambda ↔ RDS pgvector(shared, VPC 배치)
#   [조치]    approver 승인 → console-backend가 engine Step Functions StartExecution
#
# ⚠️ 실 apply 전 채울 것: acm_certificate_arn(도메인+ACM) · saml_metadata_url(진우 Entra)
#    · remediation_state_machine_arn(engine output) · console-backend `npm run build`(dist)
#
# 구역: [TF·BACKEND] [PROVIDER] [SHARED refs] [FRONT S3+CF] [COGNITO] [BACKEND LAMBDA] [ALB]
# =============================================================================

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.95" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
  }
  backend "s3" {
    bucket       = "cnapp-agentic-tfstate"
    key          = "infra/console/terraform.tfstate"
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
      Layer     = "console"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket = var.tfstate_bucket
    key    = "infra/shared/terraform.tfstate"
    region = var.region
  }
}

locals {
  vpc_id          = data.terraform_remote_state.shared.outputs.vpc_id
  public_subnets  = data.terraform_remote_state.shared.outputs.public_subnet_ids
  private_subnets = data.terraform_remote_state.shared.outputs.private_subnet_ids
  rds_secret_arn  = data.terraform_remote_state.shared.outputs.rds_secret_arn
  rds_endpoint    = data.terraform_remote_state.shared.outputs.rds_endpoint
  bedrock_policy  = data.terraform_remote_state.shared.outputs.bedrock_invoke_policy_arn
  account_id      = data.aws_caller_identity.current.account_id
  saml_enabled    = var.saml_metadata_url != ""
  has_cert        = var.acm_certificate_arn != "" # 인증서 있어야 HTTPS+authenticate-cognito 활성(단계별 apply)
  sfn_arn         = var.remediation_state_machine_arn != "" ? var.remediation_state_machine_arn : "arn:aws:states:${var.region}:${local.account_id}:stateMachine:${var.project}-remediation"
}

# =============================================================================
# [FRONT] S3(정적 자산, 비공개) + CloudFront(OAC) — apps/console 빌드 산출물
# =============================================================================
resource "aws_s3_bucket" "front" {
  bucket        = "${var.project}-console-front-${local.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "front" {
  bucket                  = aws_s3_bucket.front.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "front" {
  bucket = aws_s3_bucket.front.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

# ── 프론트 정적 자산 업로드 (고도화 2026-07-03) ──────────────────────────
# 이전엔 버킷만 만들고 dist 업로드가 없어 CloudFront가 403이었음(라이브 apply에서 발견).
# apps/console 빌드 산출물(dist/**)을 버킷에 올린다. content_type을 확장자로 매핑해야
# 브라우저가 JS/CSS/HTML을 올바로 실행/렌더(안 하면 text/plain로 떨어져 SPA 안 뜸).
# 선행: apps/console에서 `npm run build`(dist 생성). ⚠️ 갱신 후엔 CloudFront 무효화 필요
#   (aws cloudfront create-invalidation --distribution-id <id> --paths "/*") — TF 네이티브 리소스 없음.
locals {
  front_dist = "${path.module}/../../apps/console/dist"
  front_mime = {
    ".html"  = "text/html"
    ".js"    = "application/javascript"
    ".css"   = "text/css"
    ".svg"   = "image/svg+xml"
    ".json"  = "application/json"
    ".ico"   = "image/x-icon"
    ".map"   = "application/json"
    ".png"   = "image/png"
    ".woff2" = "font/woff2"
  }
}

resource "aws_s3_object" "front" {
  for_each     = fileset(local.front_dist, "**")
  bucket       = aws_s3_bucket.front.id
  key          = each.value
  source       = "${local.front_dist}/${each.value}"
  etag         = filemd5("${local.front_dist}/${each.value}")
  content_type = lookup(local.front_mime, try(regex("\\.[a-zA-Z0-9]+$", each.value), ""), "application/octet-stream")
}

resource "aws_cloudfront_origin_access_control" "front" {
  name                              = "${var.project}-console-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "front" {
  enabled             = true
  default_root_object = "index.html"
  comment             = "${var.project} console SPA"

  origin {
    domain_name              = aws_s3_bucket.front.bucket_regional_domain_name
    origin_id                = "s3-front"
    origin_access_control_id = aws_cloudfront_origin_access_control.front.id
  }

  default_cache_behavior {
    target_origin_id       = "s3-front"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    # AWS 관리 캐시 정책 CachingOptimized
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  # SPA 라우팅: 없는 경로는 index.html로(클라이언트 라우터가 처리)
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  # 커스텀 도메인(활성 시) — domain-sso.tf의 ACM 인증서(us-east-1)와 짝. 기본(off)이면 [].
  aliases = var.enable_custom_domain ? [var.domain_name] : []

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    cloudfront_default_certificate = var.enable_custom_domain ? null : true
    acm_certificate_arn            = var.enable_custom_domain ? aws_acm_certificate_validation.cf[0].certificate_arn : null
    ssl_support_method             = var.enable_custom_domain ? "sni-only" : null
    minimum_protocol_version       = var.enable_custom_domain ? "TLSv1.2_2021" : null
  }
}

# CloudFront(OAC)만 S3 읽기 허용
data "aws_iam_policy_document" "front" {
  statement {
    sid       = "AllowCloudFront"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.front.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.front.arn]
    }
  }
}
resource "aws_s3_bucket_policy" "front" {
  bucket = aws_s3_bucket.front.id
  policy = data.aws_iam_policy_document.front.json
}

# =============================================================================
# [COGNITO] User Pool(허브) ← Entra(SAML IdP) · custom:groups → viewer/approver(§7)
# =============================================================================
resource "aws_cognito_user_pool" "this" {
  name = "${var.project}-console"

  # Entra 그룹 클레임을 담을 커스텀 속성 → 토큰 custom:groups → ALB x-amzn-oidc-data
  schema {
    name                     = "groups"
    attribute_data_type      = "String"
    mutable                  = true
    developer_only_attribute = false
    string_attribute_constraints {
      min_length = 0
      max_length = 2048
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = true # 실제 사용자는 Entra 페더레이션으로만
  }
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = var.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.this.id
}

# Entra SAML IdP(메타데이터 URL 있을 때만) — attribute mapping: SAML group → custom:groups
resource "aws_cognito_identity_provider" "entra" {
  count         = local.saml_enabled ? 1 : 0
  user_pool_id  = aws_cognito_user_pool.this.id
  provider_name = "EntraID"
  provider_type = "SAML"

  provider_details = {
    MetadataURL = var.saml_metadata_url
  }

  # groups 클레임 값 = 그룹 GUID[](Entra 무료 티어 "보안 그룹" 모드 — 이름 내보내기 불가).
  # auth.ts가 approver 그룹 GUID로 매칭. custom:groups 대상키는 custom: 접두 정식(console §7·manual-infra §3.6.5).
  attribute_mapping = {
    email           = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
    "custom:groups" = "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups"
  }
}

resource "aws_cognito_user_pool_client" "this" {
  name         = "${var.project}-console-alb"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret                      = true # ALB authenticate-cognito는 시크릿 클라이언트
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]

  supported_identity_providers = local.saml_enabled ? ["EntraID"] : ["COGNITO"]

  # ALB 인증 콜백(고정 경로) — HTTPS 도메인 확정 후 실 도메인으로 교체 가능
  callback_urls = ["https://${aws_lb.this.dns_name}/oauth2/idpresponse"]
  logout_urls   = ["https://${aws_cloudfront_distribution.front.domain_name}"]

  depends_on = [aws_cognito_identity_provider.entra]
}

# =============================================================================
# [BACKEND LAMBDA] console-backend(Node) — ALB 타깃 · VPC(RDS) · read-only 기본
#   ⚠️ dist 필요: `cd apps/console-backend && npm ci && npm run build` 선행(CI 빌드 스텝)
# =============================================================================
data "archive_file" "backend" {
  type        = "zip"
  source_dir  = "${path.module}/../../apps/console-backend/dist"
  output_path = "${path.module}/build/console-backend.zip"
}

resource "aws_security_group" "backend_lambda" {
  name        = "${var.project}-console-backend"
  description = "console-backend Lambda egress (RDS, Bedrock, SFn)"
  vpc_id      = local.vpc_id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "backend" {
  name               = "${var.project}-console-backend"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "backend_vpc" {
  role       = aws_iam_role.backend.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}
resource "aws_iam_role_policy_attachment" "backend_bedrock" {
  role       = aws_iam_role.backend.name
  policy_arn = local.bedrock_policy # /chat 자연어 질의 시 Bedrock(§4·§8)
}

# read-only 기본(§10·§17): 로그 + RDS 시크릿 읽기 + 조치는 StartExecution만(변경 API 없음)
data "aws_iam_policy_document" "backend" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${local.account_id}:*"]
  }
  statement {
    sid       = "ReadDbSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.rds_secret_arn]
  }
  statement {
    sid       = "StartRemediationOnly"
    actions   = ["states:StartExecution"] # 조치는 트리거만 — 실행은 격상 역할(engine)
    resources = [local.sfn_arn]
  }
}
resource "aws_iam_role_policy" "backend" {
  name   = "backend"
  role   = aws_iam_role.backend.id
  policy = data.aws_iam_policy_document.backend.json
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/aws/lambda/${var.project}-console-backend"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "backend" {
  function_name    = "${var.project}-console-backend"
  role             = aws_iam_role.backend.arn
  runtime          = "nodejs20.x"
  handler          = "handler.handler" # dist/handler.js export handler
  filename         = data.archive_file.backend.output_path
  source_code_hash = data.archive_file.backend.output_base64sha256
  timeout          = 30
  memory_size      = 512
  vpc_config {
    subnet_ids         = local.private_subnets
    security_group_ids = [aws_security_group.backend_lambda.id]
  }
  environment {
    variables = {
      USE_MOCK      = var.use_mock
      DB_HOST       = local.rds_endpoint
      DB_SECRET_ARN = local.rds_secret_arn
      SFN_ARN       = local.sfn_arn
    }
  }
  depends_on = [aws_cloudwatch_log_group.backend, aws_iam_role_policy_attachment.backend_vpc]
}

# =============================================================================
# [ALB] authenticate-cognito(HTTPS) → Lambda 타깃 그룹 (타깃 EKS와 분리)
# =============================================================================
resource "aws_security_group" "alb" {
  name        = "${var.project}-console-alb"
  description = "console ALB 80/443 from internet"
  vpc_id      = local.vpc_id
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTP redirect"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb" "this" {
  name               = "${var.project}-console"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = local.public_subnets
}

resource "aws_lb_target_group" "backend" {
  name        = "${var.project}-console-be"
  target_type = "lambda"
}

resource "aws_lambda_permission" "alb" {
  statement_id  = "AllowALBInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backend.function_name
  principal     = "elasticloadbalancing.amazonaws.com"
  source_arn    = aws_lb_target_group.backend.arn
}

resource "aws_lb_target_group_attachment" "backend" {
  target_group_arn = aws_lb_target_group.backend.arn
  target_id        = aws_lambda_function.backend.arn
  depends_on       = [aws_lambda_permission.alb]
}

# HTTP:80 — cert 있으면 443 리다이렉트(SSO 경로), 없으면 Lambda로 직접 forward(무인증 데모/단계별 apply).
# → acm_certificate_arn 없이도 이 레이어가 apply되고 API가 HTTP로 동작(SSO는 cert 확보 후 활성).
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  dynamic "default_action" {
    for_each = local.has_cert ? [1] : []
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
  dynamic "default_action" {
    for_each = local.has_cert ? [] : [1]
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.backend.arn
    }
  }
}

# HTTPS:443 → authenticate-cognito(order 1) → forward to Lambda(order 2)
# authenticate-cognito는 HTTPS(=ACM 인증서) 필수 → cert 있을 때만 생성(count). 없으면 위 HTTP로 동작.
resource "aws_lb_listener" "https" {
  count             = local.has_cert ? 1 : 0
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type  = "authenticate-cognito"
    order = 1
    authenticate_cognito {
      user_pool_arn       = aws_cognito_user_pool.this.arn
      user_pool_client_id = aws_cognito_user_pool_client.this.id
      user_pool_domain    = aws_cognito_user_pool_domain.this.domain
    }
  }
  default_action {
    type             = "forward"
    order            = 2
    target_group_arn = aws_lb_target_group.backend.arn
  }
}
