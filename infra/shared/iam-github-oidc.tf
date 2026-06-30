# GitHub OIDC → IAM Role (D4, 키 없음). CI가 AssumeRoleWithWebIdentity로 임시 자격증명.
# sub를 우리 레포로 제한 → 다른 레포가 이 역할 못 씀.

data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github.certificates[0].sha1_fingerprint]
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "github_ci" {
  name               = "${var.project}-github-ci"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
}

# TODO: CI 최소권한 정책 attach (ECR push, EKS describe, 해당 infra/<영역> apply 범위).
#       데모 초기엔 넓게 시작해도 되나 최소권한으로 좁히는 게 목표(거버넌스 17번).
