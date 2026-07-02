output "correlation_lambda_arn" {
  value = aws_lambda_function.correlation.arn
}

output "orchestrator_lambda_arn" {
  value = aws_lambda_function.orchestrator.arn
}

# console-backend가 approver 승인 시 StartExecution할 조치 상태머신.
# infra/console에 -var 'remediation_state_machine_arn=<이 값>'로 주입(또는 remote_state).
output "remediation_state_machine_arn" {
  description = "HITL 조치 Step Functions ARN(콘솔 StartExecution 대상)"
  value       = aws_sfn_state_machine.remediation.arn
}
