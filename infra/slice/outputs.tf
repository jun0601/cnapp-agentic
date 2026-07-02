output "bucket_name" {
  description = "생성된 슬라이스 버킷 이름"
  value       = aws_s3_bucket.pii.bucket
}

output "resource_id" {
  description = "엔진에 넣을 캐논 resource_id(4.4.1a) — RealToolExecutor 입력값"
  value       = "aws:s3_bucket:${aws_s3_bucket.pii.bucket}"
}
