# EKS — terraform-aws-modules/eks. spot 작은 노드(비용), IRSA(D5), scale-to-0 가능.
# project-draft D6(EKS+ArgoCD), 22번(spot·scale-0).

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.24"

  cluster_name    = "${var.project}-shared"
  cluster_version = var.eks_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # 데모 편의로 퍼블릭 엔드포인트 허용. TODO: 운영자 IP allowlist 또는 private 전환.
  cluster_endpoint_public_access = true

  enable_irsa = true # IRSA — 파드 키리스 자격증명(D5)

  # 운영자 IAM 사용자에 cluster admin (API access entry)
  authentication_mode                      = "API_AND_CONFIG_MAP"
  enable_cluster_creator_admin_permissions = true

  access_entries = {
    for arn in var.cluster_admin_principal_arns : arn => {
      principal_arn = arn
      policy_associations = {
        admin = {
          policy_arn   = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = { type = "cluster" }
        }
      }
    }
  }

  eks_managed_node_groups = {
    default = {
      ami_type       = "AL2023_x86_64_STANDARD"
      instance_types = var.node_instance_types
      capacity_type  = "SPOT" # 비용(22번)

      min_size     = var.node_min
      max_size     = var.node_max
      desired_size = var.node_desired
    }
  }

  tags = { Layer = "shared" }
}
