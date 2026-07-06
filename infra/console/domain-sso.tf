# =============================================================================
# infra/console — 커스텀 도메인 + SSO 활성 (옵션 B: SPA가 Cognito Hosted UI로 직접 OIDC)
# 2026-07-03 신설. project-draft §10(SSO) · manual-infra §3.7
#
# 구조 결정(2026-07-03, 준형): 인증 게이트 = "SPA가 Cognito Hosted UI로 직접 로그인".
#   프론트(CloudFront, cnapp-agentic.cloud) → 로그인 클릭 → Cognito Hosted UI(OIDC/PKCE)
#     → Entra(SAML) → 코드 반환 → SPA가 토큰 교환 → custom:groups로 viewer/approver 표시.
#   (기존 ALB authenticate-cognito 흐름은 이 방식엔 불필요 — ALB는 API 백엔드로만 유지.)
#
# ⚠️ 전부 var.enable_custom_domain 토글 gated(기본 false) — DNS 위임+ACM 검증 전엔 apply 무영향.
#    켜는 순서(다음 세션): ① 가비아 네임서버 → Route53 위임 확인(dig) → ② -var enable_custom_domain=true apply.
# ⚠️ 선행(수동 1회): 가비아 네임서버를 Route53 호스팅영역(CLI 생성, 영구)으로 위임. manual-infra §3.7.
# ⚠️ 프론트 앱 코드(별도 TODO): apps/console에 OIDC 로그인 배선(Login→Hosted UI redirect, /callback 코드교환,
#    ID토큰 custom:groups→역할). 빌드 시 spa_cognito_client_id·cognito_hosted_ui_domain·domain 주입.
# =============================================================================

# CloudFront용 ACM 인증서는 반드시 us-east-1(버지니아) — CloudFront 규칙.
provider "aws" {
  alias  = "use1"
  region = "us-east-1"
  default_tags {
    tags = {
      Project   = var.project
      Env       = var.env
      Layer     = "console"
      ManagedBy = "terraform"
    }
  }
}

# CLI로 만든 호스팅 영역(영구 — terraform이 소유/삭제 안 함, 레코드만 추가) 참조.
data "aws_route53_zone" "this" {
  count = var.enable_custom_domain ? 1 : 0
  name  = "${var.domain_name}."
}

# ── CloudFront용 ACM 인증서(us-east-1) + DNS 검증 ──────────────────────
resource "aws_acm_certificate" "cf" {
  count             = var.enable_custom_domain ? 1 : 0
  provider          = aws.use1
  domain_name       = var.domain_name
  validation_method = "DNS"
  lifecycle { create_before_destroy = true }
}

resource "aws_route53_record" "cf_validation" {
  for_each = var.enable_custom_domain ? {
    for o in aws_acm_certificate.cf[0].domain_validation_options :
    o.domain_name => { name = o.resource_record_name, type = o.resource_record_type, value = o.resource_record_value }
  } : {}
  zone_id         = data.aws_route53_zone.this[0].zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.value]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "cf" {
  count                   = var.enable_custom_domain ? 1 : 0
  provider                = aws.use1
  certificate_arn         = aws_acm_certificate.cf[0].arn
  validation_record_fqdns = [for r in aws_route53_record.cf_validation : r.fqdn]
}

# ── ALB용 서울(ap-northeast-2) ACM 인증서(#1 in-transit) ────────────────
# CloudFront용 인증서는 us-east-1 규칙이지만 ALB는 리전 로컬(서울)이라 별도 발급 필요.
# 같은 도메인이라 DNS 검증 CNAME이 us-east-1 인증서와 동일 → allow_overwrite로 공존.
# SAN api.<도메인> 포함 — CloudFront /api 오리진이 https-only로 이 서브도메인을 쓰는 전 구간 TLS(#1 완성).
resource "aws_acm_certificate" "alb" {
  count                     = var.enable_custom_domain ? 1 : 0
  domain_name               = var.domain_name
  subject_alternative_names = ["api.${var.domain_name}"]
  validation_method         = "DNS"
  lifecycle { create_before_destroy = true }
}

resource "aws_route53_record" "alb_cert_validation" {
  for_each = var.enable_custom_domain ? {
    for o in aws_acm_certificate.alb[0].domain_validation_options :
    o.domain_name => { name = o.resource_record_name, type = o.resource_record_type, value = o.resource_record_value }
  } : {}
  zone_id         = data.aws_route53_zone.this[0].zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.value]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "alb" {
  count                   = var.enable_custom_domain ? 1 : 0
  certificate_arn         = aws_acm_certificate.alb[0].arn
  validation_record_fqdns = [for r in aws_route53_record.alb_cert_validation : r.fqdn]
}

# ── api 서브도메인 → ALB alias ────────────────────────────────────────
# 전 구간 TLS(#1)의 마지막 조각: CloudFront /api 오리진을 ALB DNS(http-only) 대신
# api.<도메인>(https-only, 서울 ACM SAN)으로 — 뷰어→CloudFront→오리진 전 구간 암호화.
resource "aws_route53_record" "api" {
  count   = var.enable_custom_domain ? 1 : 0
  zone_id = data.aws_route53_zone.this[0].zone_id
  name    = "api.${var.domain_name}"
  type    = "A"
  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = false
  }
}

# ── 도메인(apex) → CloudFront alias(A 레코드) ─────────────────────────
resource "aws_route53_record" "apex" {
  count   = var.enable_custom_domain ? 1 : 0
  zone_id = data.aws_route53_zone.this[0].zone_id
  name    = var.domain_name
  type    = "A"
  alias {
    name                   = aws_cloudfront_distribution.front.domain_name
    zone_id                = aws_cloudfront_distribution.front.hosted_zone_id # CloudFront 고정 zone
    evaluate_target_health = false
  }
}

# ── SPA용 Cognito 앱 클라이언트 (옵션 B: public client, PKCE, 시크릿 없음) ──
# 기존 aws_cognito_user_pool_client.this("console-alb")는 ALB authenticate-cognito용(시크릿 클라이언트).
# SPA는 브라우저에서 도니 시크릿을 못 숨김 → generate_secret=false + PKCE(code flow).
resource "aws_cognito_user_pool_client" "spa" {
  count        = var.enable_custom_domain ? 1 : 0
  name         = "${var.project}-console-spa"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = local.saml_enabled ? ["EntraID"] : ["COGNITO"]

  callback_urls = [
    "https://${var.domain_name}",
    "https://${var.domain_name}/callback",
    "http://localhost:5173", # 로컬 개발
    "http://localhost:5173/callback",
  ]
  logout_urls = ["https://${var.domain_name}", "http://localhost:5173"]

  depends_on = [aws_cognito_identity_provider.entra]
}

# ── 프론트 빌드 시 주입할 값 ──────────────────────────────────────────
output "spa_cognito_client_id" {
  description = "SPA OIDC용 Cognito 앱 클라이언트 ID(프론트 VITE_COGNITO_CLIENT_ID)"
  value       = var.enable_custom_domain ? aws_cognito_user_pool_client.spa[0].id : null
}

output "cognito_hosted_ui_domain" {
  description = "Cognito Hosted UI 도메인(프론트 로그인 redirect 대상)"
  value       = "${aws_cognito_user_pool_domain.this.domain}.auth.${var.region}.amazoncognito.com"
}

output "console_custom_domain" {
  description = "관제 앱 커스텀 도메인(활성 시)"
  value       = var.enable_custom_domain ? "https://${var.domain_name}" : null
}
