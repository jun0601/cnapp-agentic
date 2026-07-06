# =============================================================================
# infra/karpenter — 동적 노드 오토스케일러 (레이어드: shared 다음, 클러스터 런타임 레이어)
# project-draft §4.6·§22 · gitops/README(오토스케일)
#
# ★ 2026-07-03 infra/shared에서 분리해 신설.
#   이유(구조 결함 해소): shared는 '순수 AWS 폴대'여야 하는데 Karpenter(helm·kubectl provider)가
#   섞이면서 폴대가 '라이브 EKS 클러스터'에 의존하게 됨 → apply 시 컨트롤러 helm이 안 뜨면
#   shared 전체 apply가 실패(2026-07-03 context deadline exceeded), destroy 때도 helm state를
#   수동으로 만져야 했음. Karpenter를 별도 레이어로 떼어내 실패·수명주기를 격리한다.
#
# 구성: ① karpenter 서브모듈(컨트롤러 IRSA + 노드 IAM 역할 + spot 중단 SQS·EventBridge)
#       ② helm_release(karpenter 컨트롤러, kube-system)
#       ③ EC2NodeClass + NodePool(CRD) — 노드 스펙·제약
# 노드 발견: shared가 서브넷·노드SG에 부착한 `karpenter.sh/discovery = <cluster>` 태그로 조회.
#
# 의존: infra/shared(EKS 클러스터·OIDC provider·discovery 태그) — remote_state로 참조.
# apply 순서: shared → (이 레이어) → target·backend·console → monitoring.
# destroy 순서: 역순 — 이 레이어는 shared '직전'에 destroy(NodePool 삭제 → Karpenter가 자기 노드
#   드레인 → helm 제거). shared보다 먼저 지워야 EKS/VPC가 노드 남긴 채 destroy 안 됨.
#
# ⚠️ 프리티어 계정 제약(2026-07-03 확인): 적격 타입만 RunInstances 허용(t3.micro/small·t4g.micro/small).
#    NodePool을 t3.small/t3.micro(amd64) 스팟으로 제한. 안 그러면 Karpenter가 큰 인스턴스
#    띄우려다 NAT 때와 같은 InvalidParameterCombination(Free Tier) 거부됨.
# ⚠️ 컨트롤러·CRD는 라이브 클러스터에 적용 → helm/kubectl provider가 EKS에 인증(aws eks get-token).
#    apply 머신에 aws CLI + 클러스터 admin 자격 필요(shared 생성자 jh_lee 또는 access entry 등록자).
# =============================================================================

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.95" }
    helm    = { source = "hashicorp/helm", version = "~> 2.12" }      # Karpenter 컨트롤러 설치
    kubectl = { source = "gavinbunney/kubectl", version = "~> 1.14" } # NodePool·EC2NodeClass CRD 적용
  }
  backend "s3" {
    bucket       = "cnapp-agentic-tfstate"
    key          = "infra/karpenter/terraform.tfstate"
    region       = "ap-northeast-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project   = var.project
      Env       = var.env
      Layer     = "karpenter"
      ManagedBy = "terraform"
    }
  }
}

# ── infra/shared 출력 참조(EKS 클러스터명·OIDC provider ARN) ──────────────
data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket = var.tfstate_bucket
    key    = "infra/shared/terraform.tfstate"
    region = var.region
  }
}

# 클러스터 엔드포인트·CA는 EKS API에서 직접 조회(remote_state 출력면 최소화). 클러스터가
# 이미 존재할 때만 읽히므로 이 레이어는 shared apply '이후'에만 apply(순서 강제 스크립트 참고).
data "aws_eks_cluster" "this" {
  name = local.cluster_name
}

locals {
  cluster_name = data.terraform_remote_state.shared.outputs.eks_cluster_name
}

# ── EKS 인증 provider(helm·kubectl) — aws eks get-token exec ──────────────
provider "helm" {
  kubernetes {
    host                   = data.aws_eks_cluster.this.endpoint
    cluster_ca_certificate = base64decode(data.aws_eks_cluster.this.certificate_authority[0].data)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", local.cluster_name, "--region", var.region]
    }
  }
}

provider "kubectl" {
  host                   = data.aws_eks_cluster.this.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.this.certificate_authority[0].data)
  load_config_file       = false
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", local.cluster_name, "--region", var.region]
  }
}

# ── ① Karpenter 서브모듈: 컨트롤러 IRSA + 노드 IAM 역할 + spot 중단 SQS ──
module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 20.24" # shared의 EKS 모듈과 버전 정합

  cluster_name          = local.cluster_name
  enable_v1_permissions = true # Karpenter 1.x 권한 셋

  # 컨트롤러 SA는 IRSA로 IAM 연결(shared EKS 모듈 enable_irsa=true로 OIDC 발급자 존재).
  # Pod Identity(대안)는 eks-pod-identity-agent 애드온이 별도 필요 → IRSA 채택.
  enable_irsa                     = true
  irsa_oidc_provider_arn          = data.terraform_remote_state.shared.outputs.eks_oidc_provider_arn
  irsa_namespace_service_accounts = ["kube-system:karpenter"]
  create_pod_identity_association = false

  # Karpenter가 띄우는 노드의 IAM 역할에 SSM(디버그·세션) 추가
  node_iam_role_additional_policies = {
    AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }

  tags = { Layer = "karpenter" }
}

# 모듈 v20의 v1 권한셋이 Karpenter 1.13의 instance-profile GC 컨트롤러가 쓰는
# iam:ListInstanceProfiles를 안 줘서 매 리컨실마다 AccessDenied ERROR 로그 발생(2026-07-03 실검증
# — 프로비저닝 자체는 무영향, GC만 실패). Karpenter가 만드는 instance-profile 경로(/karpenter/...)로
# 스코프한 최소 권한 1문을 보충한다.
data "aws_caller_identity" "current" {}

resource "aws_iam_role_policy" "controller_113_gc" {
  name = "karpenter-113-instanceprofile-gc"
  role = module.karpenter.iam_role_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "InstanceProfileGCList"
      Effect   = "Allow"
      Action   = ["iam:ListInstanceProfiles"]
      Resource = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:instance-profile/karpenter/*"
    }]
  })
}

# ── ② Karpenter 컨트롤러(helm) ───────────────────────────────────────
resource "helm_release" "karpenter" {
  namespace  = "kube-system"
  name       = "karpenter"
  repository = "oci://public.ecr.aws/karpenter"
  chart      = "karpenter"
  version    = var.karpenter_chart_version
  wait       = true # 컨트롤러 Deployment·CRD 준비까지 대기 → kubectl_manifest(NodePool)가 CRD 못 찾는 레이스 방지
  timeout    = 900  # 소형 클러스터 이미지 pull 여유(기존 600 → context deadline 재발 방지)

  values = [yamlencode({
    # 하드닝: 기본 replicas=2는 pod anti-affinity로 노드 2개를 요구 → 데모 2노드에선 스케줄 압박·
    # 리더선출 지연으로 helm wait 타임아웃(2026-07-03 실패 원인 후보). 데모는 1개로 충분(HA 불요).
    replicas = 1
    serviceAccount = {
      name        = "karpenter"
      annotations = { "eks.amazonaws.com/role-arn" = module.karpenter.iam_role_arn }
    }
    settings = {
      clusterName       = local.cluster_name
      interruptionQueue = module.karpenter.queue_name
    }
    # 컨트롤러는 관리형 노드그룹(스팟 t3.small)에서 돎 — 소형 리소스
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
    metadata   = { name = "cnapp-spot" }
    spec = {
      amiFamily        = "AL2023"
      amiSelectorTerms = [{ alias = "al2023@latest" }]
      role             = module.karpenter.node_iam_role_name
      subnetSelectorTerms = [{
        tags = { "karpenter.sh/discovery" = local.cluster_name }
      }]
      securityGroupSelectorTerms = [{
        tags = { "karpenter.sh/discovery" = local.cluster_name }
      }]
      # Karpenter가 띄우는 EC2 인스턴스 태그 — EC2 콘솔 Name이 'default'/공란 대신 프로젝트명으로.
      tags = { Name = "${local.cluster_name}-karpenter-spot" }
    }
  })
  depends_on = [helm_release.karpenter]
}

resource "kubectl_manifest" "nodepool" {
  yaml_body = yamlencode({
    apiVersion = "karpenter.sh/v1"
    kind       = "NodePool"
    metadata   = { name = "cnapp-spot" }
    spec = {
      template = {
        spec = {
          nodeClassRef = { group = "karpenter.k8s.aws", kind = "EC2NodeClass", name = "cnapp-spot" }
          requirements = [
            # 프리티어 적격 amd64만(계정 제약 §21 — 그 밖 타입은 RunInstances가 Free Tier 거부).
            { key = "node.kubernetes.io/instance-type", operator = "In", values = ["t3.small", "t3.micro"] },
            { key = "kubernetes.io/arch", operator = "In", values = ["amd64"] },
            # 혼합 용량 전략: spot 우선(비용) + on-demand 폴백(연속성). Karpenter는 항상 더 싼
            # spot을 먼저 시도하고, 스팟 재고 부족·회수 시 자동으로 on-demand로 폴백해 파드를 살린다.
            # 스팟이 잘 잡히는 평상시엔 추가비용 0. (프로덕션 분리 패턴은 README '용량 전략' 참고)
            { key = "karpenter.sh/capacity-type", operator = "In", values = ["spot", "on-demand"] },
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
