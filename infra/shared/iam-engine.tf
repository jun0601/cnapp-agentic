# 엔진 IAM 정책 2종 — 계약과 동기화.
# (1) Evidence read-only — contracts/evidence-allowlist.json과 1:1. 변경 API 절대 없음(거버넌스 17번).
# (2) Bedrock invoke — 에이전트 LLM 호출.
# 실행 역할(Lambda) 자체는 infra/engine에서 만들고 여기 정책 ARN을 attach.

data "aws_iam_policy_document" "evidence_readonly" {
  statement {
    sid    = "EvidenceReadOnly"
    effect = "Allow"
    actions = [
      "s3:GetBucketPolicy",
      "s3:GetBucketAcl",
      "s3:GetPublicAccessBlock",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:SimulatePrincipalPolicy",
      "macie2:GetFindings",
      "ec2:DescribeSecurityGroups",
      "accessanalyzer:ListFindings"
    ]
    resources = ["*"] # 전부 read-only라 * 허용 가능. TODO: 가능한 액션은 리소스 좁히기.
  }
}

resource "aws_iam_policy" "evidence_readonly" {
  name        = "${var.project}-evidence-readonly"
  description = "Evidence 에이전트 read-only allowlist (contracts/evidence-allowlist.json)"
  policy      = data.aws_iam_policy_document.evidence_readonly.json
}

data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid       = "BedrockInvoke"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = ["*"] # TODO: 서울 가용 모델 ARN으로 좁히기(haiku·sonnet·titan-embed). 모델 액세스 콘솔 활성화 선행.
  }
}

resource "aws_iam_policy" "bedrock_invoke" {
  name        = "${var.project}-bedrock-invoke"
  description = "에이전트 Bedrock InvokeModel"
  policy      = data.aws_iam_policy_document.bedrock_invoke.json
}
