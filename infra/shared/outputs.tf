# 다른 레이어(infra/target·console·scanners·pipeline·engine)가 참조할 출력.
# 영역별 state는 terraform_remote_state로 이 출력을 읽는다(4.6).

output "vpc_id" {
  value = module.vpc.vpc_id
}

output "private_subnet_ids" {
  value = module.vpc.private_subnets
}

output "public_subnet_ids" {
  value = module.vpc.public_subnets
}

output "eks_cluster_name" {
  value = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "eks_oidc_provider_arn" {
  description = "IRSA용 OIDC provider ARN"
  value       = module.eks.oidc_provider_arn
}

output "ecr_repository_urls" {
  value = { for k, r in aws_ecr_repository.this : k => r.repository_url }
}

output "rds_endpoint" {
  value = aws_db_instance.pgvector.address
}

output "rds_secret_arn" {
  description = "RDS 마스터 자격증명 Secrets Manager ARN"
  value       = aws_secretsmanager_secret.db.arn
}

output "rds_security_group_id" {
  value = aws_security_group.rds.id
}

output "github_ci_role_arn" {
  value = aws_iam_role.github_ci.arn
}

output "evidence_readonly_policy_arn" {
  value = aws_iam_policy.evidence_readonly.arn
}

output "bedrock_invoke_policy_arn" {
  value = aws_iam_policy.bedrock_invoke.arn
}
