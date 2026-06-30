provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project
      Env       = var.env
      ManagedBy = "terraform"
      Layer     = "shared"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
