# S3 원격 백엔드 — manual-infra.md 2번에서 콘솔/CLI로 만든 state 버킷 사용.
# DynamoDB 락 테이블 미사용 → S3 네이티브 락(use_lockfile, TF 1.10+).
#
# ⚠️ apply 전: bucket 값을 manual-infra 2번에서 만든 실제 버킷명으로 교체.
#    backend 블록은 변수를 못 받으므로 하드코딩하거나 `-backend-config`로 주입.
#    예) terraform init -backend-config="bucket=cnapp-tfstate-xxxxx"

terraform {
  backend "s3" {
    bucket       = "TODO-cnapp-tfstate-CHANGEME" # manual-infra 2번 실제 버킷명
    key          = "infra/shared/terraform.tfstate"
    region       = "ap-northeast-2"
    encrypt      = true
    use_lockfile = true
  }
}
