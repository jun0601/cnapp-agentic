# ECR — 워크로드 이미지 레지스트리(D6). scan_on_push=true로 Inspector 취약점 탐지(D14).
# ※ 타깃 앱의 '의도적' 결함(latest 태그 사용·스캔 미설정 finding 등)은 infra/target에서 별도 구성.
#    여기 shared 레지스트리는 안전 기본값.

locals {
  ecr_repos = ["product", "order", "member", "console-backend"]
}

resource "aws_ecr_repository" "this" {
  for_each = toset(local.ecr_repos)

  name                 = "${var.project}/${each.value}"
  image_tag_mutability = "MUTABLE" # 데모. 공급망 강화 시 IMMUTABLE(D17)

  image_scanning_configuration {
    scan_on_push = true
  }

  force_delete = true # 데모 — destroy 편의
}
