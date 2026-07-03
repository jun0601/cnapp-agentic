# Karpenter 레이어 출력 — 관측·디버그용(다른 레이어가 필수로 참조하진 않음).

output "karpenter_node_iam_role_name" {
  description = "Karpenter가 띄우는 노드의 IAM 역할 이름"
  value       = module.karpenter.node_iam_role_name
}

output "karpenter_controller_iam_role_arn" {
  description = "Karpenter 컨트롤러 IRSA 역할 ARN"
  value       = module.karpenter.iam_role_arn
}

output "karpenter_interruption_queue" {
  description = "Spot 중단 처리용 SQS 큐 이름"
  value       = module.karpenter.queue_name
}
