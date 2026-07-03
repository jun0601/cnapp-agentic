# =============================================================================
# infra/shared — Karpenter (동적 노드 오토스케일러) — 2026-07-03 신설
# project-draft §22 · gitops/autoscaling/karpenter.yaml(이제 이 코드가 컨트롤러를 설치)
#
# 구성: ① karpenter 서브모듈(컨트롤러 IRSA + 노드 IAM 역할 + spot 중단 SQS·EventBridge)
#       ② helm_release(karpenter 컨트롤러, kube-system)
#       ③ EC2NodeClass + NodePool(CRD) — 노드 스펙·제약
# 노드 발견: 서브넷·노드SG의 `karpenter.sh/discovery = <cluster>` 태그(main.tf에서 부착).
#
# ⚠️ 프리티어 계정 제약(2026-07-03 확인): 적격 타입만 RunInstances 허용(t3.micro/small·t4g.micro/small).
#    → NodePool을 t3.small/t3.micro(amd64) 스팟으로 제한. 안 그러면 Karpenter가 큰 인스턴스
#      띄우려다 NAT 때와 같은 InvalidParameterCombination(Free Tier) 거부됨.
# ⚠️ 컨트롤러·CRD는 라이브 클러스터에 적용 → helm/kubectl provider가 EKS에 인증(aws eks get-token).
#    apply 머신에 aws CLI + 클러스터 admin 자격 필요. 관리형 노드그룹은 유지(컨트롤러·시스템 파드용
#    베이스), Karpenter는 그 위에 워크로드용 노드를 추가 프로비저닝.
# =============================================================================

# ── EKS 인증 provider(helm·kubectl) ──────────────────────────────────
provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--region", var.region]
    }
  }
}

provider "kubectl" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  load_config_file       = false
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--region", var.region]
  }
}

# ── ① Karpenter 서브모듈: 컨트롤러 IRSA + 노드 IAM 역할 + spot 중단 SQS ──
module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 20.24" # EKS 모듈과 버전 정합

  cluster_name          = module.eks.cluster_name
  enable_v1_permissions = true # Karpenter 1.x 권한 셋

  # 컨트롤러 SA는 IRSA로 IAM 연결(EKS 모듈 enable_irsa=true로 OIDC 발급자 존재).
  # Pod Identity(대안)는 eks-pod-identity-agent 애드온이 별도 필요 → IRSA 채택.
  enable_irsa                     = true
  irsa_oidc_provider_arn          = module.eks.oidc_provider_arn
  irsa_namespace_service_accounts = ["kube-system:karpenter"]
  create_pod_identity_association = false

  # Karpenter가 띄우는 노드의 IAM 역할에 SSM(디버그·세션) 추가
  node_iam_role_additional_policies = {
    AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }

  tags = { Layer = "shared" }
}

# ── ② Karpenter 컨트롤러(helm) ───────────────────────────────────────
resource "helm_release" "karpenter" {
  namespace  = "kube-system"
  name       = "karpenter"
  repository = "oci://public.ecr.aws/karpenter"
  chart      = "karpenter"
  version    = var.karpenter_chart_version
  wait       = true # 컨트롤러 Deployment·CRD 준비까지 대기 → 이후 kubectl_manifest(NodePool)가 CRD 못 찾는 레이스 방지
  timeout    = 600

  values = [yamlencode({
    serviceAccount = {
      name        = "karpenter"
      annotations = { "eks.amazonaws.com/role-arn" = module.karpenter.iam_role_arn }
    }
    settings = {
      clusterName       = module.eks.cluster_name
      interruptionQueue = module.karpenter.queue_name
    }
    # 컨트롤러는 관리형 노드그룹(온디맨드/스팟 t3.small)에서 돎 — 소형 리소스
    controller = {
      resources = {
        requests = { cpu = "0.25", memory = "256Mi" }
        limits   = { cpu = "0.5", memory = "512Mi" }
      }
    }
  })]
}

# ── ③ EC2NodeClass + NodePool (Karpenter CRD) ────────────────────────
# ⚠️ 프리티어 제한: t3.small/t3.micro(amd64) 스팟만 — 계정이 그 밖 타입 RunInstances 거부.
resource "kubectl_manifest" "ec2nodeclass" {
  yaml_body = yamlencode({
    apiVersion = "karpenter.k8s.aws/v1"
    kind       = "EC2NodeClass"
    metadata   = { name = "default" }
    spec = {
      amiFamily        = "AL2023"
      amiSelectorTerms = [{ alias = "al2023@latest" }]
      role             = module.karpenter.node_iam_role_name
      subnetSelectorTerms = [{
        tags = { "karpenter.sh/discovery" = module.eks.cluster_name }
      }]
      securityGroupSelectorTerms = [{
        tags = { "karpenter.sh/discovery" = module.eks.cluster_name }
      }]
    }
  })
  depends_on = [helm_release.karpenter]
}

resource "kubectl_manifest" "nodepool" {
  yaml_body = yamlencode({
    apiVersion = "karpenter.sh/v1"
    kind       = "NodePool"
    metadata   = { name = "default" }
    spec = {
      template = {
        spec = {
          nodeClassRef = { group = "karpenter.k8s.aws", kind = "EC2NodeClass", name = "default" }
          requirements = [
            # 프리티어 적격 amd64 스팟만(계정 제약)
            { key = "node.kubernetes.io/instance-type", operator = "In", values = ["t3.small", "t3.micro"] },
            { key = "kubernetes.io/arch", operator = "In", values = ["amd64"] },
            { key = "karpenter.sh/capacity-type", operator = "In", values = ["spot"] },
          ]
        }
      }
      limits = { cpu = "8" } # 데모 상한(무한 스케일 방지)
      disruption = {
        consolidationPolicy = "WhenEmptyOrUnderutilized"
        consolidateAfter    = "30s" # 유휴 노드 빠르게 정리(비용)
      }
    }
  })
  depends_on = [kubectl_manifest.ec2nodeclass]
}
