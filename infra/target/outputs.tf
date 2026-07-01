output "member_pii_bucket" {
  value = aws_s3_bucket.member_pii.bucket
}

output "member_irsa_role_arn" {
  value       = aws_iam_role.member_irsa.arn
  description = "member ServiceAccount에 주입(k8s serviceaccount annotation)"
}

output "order_irsa_role_arn" {
  value       = aws_iam_role.order_irsa.arn
  description = "order ServiceAccount에 주입"
}

output "open_sg_id" {
  value       = try(aws_security_group.open_ingress[0].id, null)
  description = "f3 토글 시에만 생성"
}

output "enabled_defects" {
  value = {
    f6_s3_public     = var.enable_s3_public
    f3_open_sg       = var.enable_open_sg
    f4_overpriv_irsa = var.enable_overpriv_irsa
  }
  description = "현재 켜진 결함 토글(데모 회귀 확인용)"
}
