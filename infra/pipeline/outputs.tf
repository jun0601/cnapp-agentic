output "ingest_queue_url" {
  description = "ingest→normalize 버퍼 큐 URL"
  value       = aws_sqs_queue.ingest.url
}

output "ingest_queue_arn" {
  value = aws_sqs_queue.ingest.arn
}

output "ingest_lambda_arn" {
  value = aws_lambda_function.ingest.arn
}

output "normalize_lambda_arn" {
  value = aws_lambda_function.normalize.arn
}

# infra/engine이 구독하는 상관 트리거 이벤트(정규화 완료 후 normalize가 PutEvents로 발행).
# 계약: source="cnapp.findings", detail-type="cnapp.findings.batch.completed" (console-app-design §14)
output "batch_completed_event_source" {
  description = "정규화 배치 완료 이벤트 소스(engine 상관 Lambda 규칙에서 매칭)"
  value       = "cnapp.findings"
}
