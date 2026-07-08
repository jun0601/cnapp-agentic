# =============================================================================
# infra/console — WAF (CloudFront) : 관제 플랫폼 자체 보호(도그푸딩, 2026-07-08)
#
# 왜 CloudFront에 붙이나: 뷰어는 SPA(정적)든 /api(백엔드 프록시)든 전부 CloudFront를
#   거쳐 들어온다 → 여기 하나면 콘솔 진입점 전체가 L7 방어 뒤로 들어간다.
# 왜 us-east-1(aws.use1): WAFv2 scope=CLOUDFRONT WebACL은 반드시 us-east-1에 생성해야
#   한다(ACM CloudFront 인증서와 동일 제약, AWS 규칙).
# 의도적 취약점과 무관: 이 WAF는 '관제 플랫폼'만 보호한다. target 앱의 의도적 결함
#   (공개 S3·열린 SG 등, findings 소스)은 전혀 안 건드린다(플랫폼 하드닝 #1~#7과 같은 스코프).
# 비용: WebACL + 관리규칙은 console 레이어와 함께 생성/삭제(destroy 시 $0). 상시 방치 안 함.
# =============================================================================

resource "aws_wafv2_web_acl" "front" {
  provider    = aws.use1
  name        = "${var.project}-console-cf"
  description = "CloudFront WAF for console SPA and API - managed rules plus rate limit"
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  # ① AWS 관리 규칙: 공통 위협(OWASP 기초 — XSS·LFI·잘못된 요청 시그니처 등)
  rule {
    name     = "AWSManagedCommon"
    priority = 1
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project}-cf-common"
      sampled_requests_enabled   = true
    }
  }

  # ② AWS 관리 규칙: 알려진 악성 입력(취약점 스캐너·익스플로잇 페이로드 시그니처)
  rule {
    name     = "AWSManagedKnownBadInputs"
    priority = 2
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project}-cf-badinputs"
      sampled_requests_enabled   = true
    }
  }

  # ③ Rate-based: 단일 IP가 5분 창에 2000요청 초과 시 차단(brute-force·L7 DDoS 완화).
  #   관제 콘솔 정상 사용은 이 임계값에 한참 못 미침 — 자동화 공격만 걸림.
  rule {
    name     = "RateLimitPerIP"
    priority = 3
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project}-cf-ratelimit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.project}-console-cf"
    sampled_requests_enabled   = true
  }
}

# ── WAF 로깅 → CloudWatch Logs(us-east-1) ─────────────────────────────
# 로그그룹 이름은 반드시 `aws-waf-logs-` 접두(AWS 규칙 — 이 접두여야 WAF가 write 권한을 얻음).
resource "aws_cloudwatch_log_group" "waf" {
  provider          = aws.use1
  name              = "aws-waf-logs-${var.project}-console-cf"
  retention_in_days = var.log_retention_days
}

resource "aws_wafv2_web_acl_logging_configuration" "front" {
  provider = aws.use1
  # log group ARN의 후행 ":*"는 WAF 로깅 대상으로는 무효 → 제거해서 전달.
  log_destination_configs = [trimsuffix(aws_cloudwatch_log_group.waf.arn, ":*")]
  resource_arn            = aws_wafv2_web_acl.front.arn

  # 민감 헤더는 로그에 안 남김(Cognito ID 토큰 등).
  redacted_fields {
    single_header {
      name = "authorization"
    }
  }
}

output "waf_web_acl_arn" {
  description = "CloudFront WAF WebACL ARN"
  value       = aws_wafv2_web_acl.front.arn
}
