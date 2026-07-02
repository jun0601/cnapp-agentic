output "cloudfront_domain" {
  description = "콘솔 프론트 접속 도메인(CloudFront)"
  value       = aws_cloudfront_distribution.front.domain_name
}

output "front_bucket" {
  description = "프론트 정적 자산 S3 버킷(apps/console 빌드 업로드 대상)"
  value       = aws_s3_bucket.front.bucket
}

output "alb_dns_name" {
  description = "API ALB DNS — 프론트 VITE_API_BASE=https://<이 값>/api"
  value       = aws_lb.this.dns_name
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.this.id
}

output "cognito_domain" {
  description = "Cognito Hosted UI 도메인 프리픽스"
  value       = aws_cognito_user_pool_domain.this.domain
}

output "console_backend_lambda_arn" {
  value = aws_lambda_function.backend.arn
}
