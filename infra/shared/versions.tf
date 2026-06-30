# infra/shared — terraform·provider 버전 고정
# project-draft 4.6(레이어드: shared 기반 먼저 apply) · manual-infra 2번(state 부트스트랩)

terraform {
  required_version = ">= 1.10" # S3 네이티브 락(use_lockfile) 지원 버전

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.95" # vpc(~>5.13)·eks(~>20.24) 모듈과 정합. NAT은 raw 리소스(모듈 충돌 회피)
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}
