# ── 데이터 평면(구 pipeline) ─────────────────────────────────────────
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

# 정규화 완료 후 normalize가 PutEvents로 발행 → 상관 Lambda 규칙에서 매칭.
# 계약: source="cnapp.findings", detail-type="cnapp.findings.batch.completed" (console-app-design §14)
output "batch_completed_event_source" {
  description = "정규화 배치 완료 이벤트 소스"
  value       = "cnapp.findings"
}

# ── 추론 평면(구 engine) ─────────────────────────────────────────────
output "correlation_lambda_arn" {
  value = aws_lambda_function.correlation.arn
}

output "orchestrator_lambda_arn" {
  value = aws_lambda_function.orchestrator.arn
}

# ── 조치(HITL) — infra/console·infra/monitoring이 참조 ────────────────
# console-backend가 approver 승인 시 StartExecution할 조치 상태머신.
# infra/console에 -var 'remediation_state_machine_arn=<이 값>'로 주입.
output "remediation_state_machine_arn" {
  description = "HITL 조치 Step Functions ARN(콘솔 StartExecution 대상)"
  value       = aws_sfn_state_machine.remediation.arn
}

output "audit_bucket" {
  description = "불변 감사 로그(S3 Object Lock) 버킷 — 조치 실행기가 기록"
  value       = aws_s3_bucket.audit.bucket
}

output "prowler_results_bucket" {
  description = "Prowler 스캔 결과 드롭 버킷(GitHub Actions prowler-scan.yml이 여기로 업로드 → ingest Lambda 자동 트리거)"
  value       = aws_s3_bucket.prowler_results.bucket
}
