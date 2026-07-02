output "grafana_irsa_role_arn" {
  description = "gitops/monitoring/values.yaml의 Grafana ServiceAccount annotation(eks.amazonaws.com/role-arn)에 넣을 값"
  value       = aws_iam_role.grafana.arn
}

output "dashboard_url" {
  description = "CloudWatch 콘솔에서 바로 열리는 대시보드 URL"
  value       = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${aws_cloudwatch_dashboard.platform.dashboard_name}"
}

output "cloudtrail_log_group_arn" {
  description = "기존(수동) CloudTrail 편집 화면의 'CloudWatch Logs' 섹션에 붙여넣을 로그그룹 ARN(1회 수동 연결, README §10)"
  value       = aws_cloudwatch_log_group.cloudtrail.arn
}

output "cloudtrail_cwl_role_arn" {
  description = "위와 함께 붙여넣을 IAM 역할 ARN(트레일이 이 역할로 로그그룹에 씀)"
  value       = aws_iam_role.cloudtrail_cwl.arn
}

output "teams_webhook_secret_arn" {
  description = "여기에 실제 webhook URL을 1회 수동 주입(aws secretsmanager put-secret-value --secret-id <이 ARN> --secret-string '<url>'). Terraform은 값을 모름."
  value       = aws_secretsmanager_secret.teams_webhook.arn
}

output "alerts_sns_topic_arn" {
  description = "CloudWatch 알람 팬아웃 지점(추가 알람을 만들 때 alarm_actions에 이 값을 씀)"
  value       = aws_sns_topic.alerts.arn
}
