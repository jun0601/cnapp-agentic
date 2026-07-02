# =============================================================================
# infra/pipeline — 수집·정규화 데이터 평면 (레이어드: shared 다음)
# project-draft §4.6 · console-app-design §9
#
# 흐름: [스캐너 findings] → EventBridge(기본 버스) → ingest Lambda → SQS
#        → normalize Lambda(SQS 소비) → OCSF-lite 정규화 → RDS(pgvector)
#        → PutEvents(cnapp.findings / batch.completed) → (infra/engine 상관 Lambda 구독)
#
# ⚠️ Lambda 패키지: 지금은 '배포 가능한 스텁'(index.handler). 실 apply/CI에서
#    pipeline/ingest·pipeline/normalize 실코드 + 의존성으로 교체(swap 포인트 = archive_file).
#    비즈니스 로직은 run_e2e.py로 로컬 검증됨 — 이 레이어는 '프로덕션 배관 모양'.
#
# 구역: [TF·BACKEND] [PROVIDER] [SHARED refs] [SQS] [IAM] [LAMBDA] [EVENTBRIDGE]
# =============================================================================

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.95" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
  }
  backend "s3" {
    bucket       = "cnapp-agentic-tfstate"
    key          = "infra/pipeline/terraform.tfstate"
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
      Layer     = "pipeline"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# infra/shared 출력 참조(VPC·private subnet·RDS)
data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket = var.tfstate_bucket
    key    = "infra/shared/terraform.tfstate"
    region = var.region
  }
}

locals {
  vpc_id          = data.terraform_remote_state.shared.outputs.vpc_id
  private_subnets = data.terraform_remote_state.shared.outputs.private_subnet_ids
  rds_secret_arn  = data.terraform_remote_state.shared.outputs.rds_secret_arn
  rds_endpoint    = data.terraform_remote_state.shared.outputs.rds_endpoint
}

# =============================================================================
# [SQS] ingest → normalize 사이 버퍼(재시도·백프레셔) + DLQ
# =============================================================================
resource "aws_sqs_queue" "ingest_dlq" {
  name                      = "${var.project}-ingest-dlq"
  message_retention_seconds = 1209600 # 14일
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "ingest" {
  name                       = "${var.project}-ingest"
  visibility_timeout_seconds = 180 # normalize Lambda timeout(60) 이상
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ingest_dlq.arn
    maxReceiveCount     = 5
  })
}

# =============================================================================
# [IAM] Lambda 실행 역할 2종
# =============================================================================
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# --- ingest 역할: 로그 + SQS 송신(EventBridge가 호출) ---
resource "aws_iam_role" "ingest" {
  name               = "${var.project}-pipeline-ingest"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "ingest" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:*"]
  }
  statement {
    sid       = "SendToQueue"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.ingest.arn]
  }
}

resource "aws_iam_role_policy" "ingest" {
  name   = "ingest"
  role   = aws_iam_role.ingest.id
  policy = data.aws_iam_policy_document.ingest.json
}

# --- normalize 역할: 로그 + SQS 소비 + Secrets(RDS) + VPC + PutEvents ---
resource "aws_iam_role" "normalize" {
  name               = "${var.project}-pipeline-normalize"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# VPC ENI 관리(RDS 접근 위해 Lambda를 VPC에 배치)
resource "aws_iam_role_policy_attachment" "normalize_vpc" {
  role       = aws_iam_role.normalize.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "normalize" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:*"]
  }
  statement {
    sid       = "ConsumeQueue"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.ingest.arn]
  }
  statement {
    sid       = "ReadDbSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.rds_secret_arn]
  }
  statement {
    sid       = "EmitBatchEvent"
    actions   = ["events:PutEvents"]
    resources = ["arn:aws:events:${var.region}:${data.aws_caller_identity.current.account_id}:event-bus/default"]
  }
}

resource "aws_iam_role_policy" "normalize" {
  name   = "normalize"
  role   = aws_iam_role.normalize.id
  policy = data.aws_iam_policy_document.normalize.json
}

# normalize Lambda용 SG(egress만 — RDS는 VPC CIDR 인바운드 허용, NAT로 AWS API)
resource "aws_security_group" "lambda" {
  name        = "${var.project}-pipeline-lambda"
  description = "pipeline normalize Lambda egress"
  vpc_id      = local.vpc_id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# =============================================================================
# [LAMBDA] 배포 가능한 스텁(실코드 스왑 포인트 = archive_file.source)
#   ⚠️ 실 apply/CI: source를 pipeline/ingest·pipeline/normalize 빌드 산출물로 교체.
# =============================================================================
data "archive_file" "ingest" {
  type        = "zip"
  output_path = "${path.module}/build/ingest.zip"
  source {
    filename = "index.py"
    content  = <<-PY
      # TODO(real apply): CI가 pipeline/ingest 실코드+deps로 교체. 지금은 배포 가능한 스텁.
      import json
      def handler(event, context):
          print("ingest:", json.dumps(event)[:500])
          return {"ok": True}
    PY
  }
}

data "archive_file" "normalize" {
  type        = "zip"
  output_path = "${path.module}/build/normalize.zip"
  source {
    filename = "index.py"
    content  = <<-PY
      # TODO(real apply): CI가 pipeline/normalize(Normalizer) 실코드+deps로 교체.
      import json
      def handler(event, context):
          print("normalize records:", len(event.get("Records", [])))
          return {"ok": True}
    PY
  }
}

resource "aws_cloudwatch_log_group" "ingest" {
  name              = "/aws/lambda/${var.project}-ingest"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "normalize" {
  name              = "/aws/lambda/${var.project}-normalize"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "ingest" {
  function_name    = "${var.project}-ingest"
  role             = aws_iam_role.ingest.arn
  runtime          = "python3.12"
  handler          = "index.handler"
  filename         = data.archive_file.ingest.output_path
  source_code_hash = data.archive_file.ingest.output_base64sha256
  timeout          = 30
  memory_size      = 256
  environment {
    variables = {
      QUEUE_URL = aws_sqs_queue.ingest.url
    }
  }
  depends_on = [aws_cloudwatch_log_group.ingest]
}

resource "aws_lambda_function" "normalize" {
  function_name    = "${var.project}-normalize"
  role             = aws_iam_role.normalize.arn
  runtime          = "python3.12"
  handler          = "index.handler"
  filename         = data.archive_file.normalize.output_path
  source_code_hash = data.archive_file.normalize.output_base64sha256
  timeout          = 60
  memory_size      = 512
  vpc_config {
    subnet_ids         = local.private_subnets
    security_group_ids = [aws_security_group.lambda.id]
  }
  environment {
    variables = {
      DB_HOST        = local.rds_endpoint
      DB_SECRET_ARN  = local.rds_secret_arn
      EVENT_BUS_NAME = "default"
    }
  }
  depends_on = [aws_cloudwatch_log_group.normalize, aws_iam_role_policy_attachment.normalize_vpc]
}

# SQS → normalize (event source mapping)
resource "aws_lambda_event_source_mapping" "sqs_to_normalize" {
  event_source_arn = aws_sqs_queue.ingest.arn
  function_name    = aws_lambda_function.normalize.arn
  batch_size       = 10
}

# =============================================================================
# [EVENTBRIDGE] Security Hub Findings Imported(기본 버스) → ingest Lambda
#   (Prowler S3 드롭·커스텀 소스는 ingest가 S3 이벤트로도 받음 — pipeline/ingest 참조)
# =============================================================================
resource "aws_cloudwatch_event_rule" "securityhub_imported" {
  name        = "${var.project}-securityhub-imported"
  description = "Security Hub Findings Imported → ingest"
  event_pattern = jsonencode({
    source        = ["aws.securityhub"]
    "detail-type" = ["Security Hub Findings - Imported"]
  })
}

resource "aws_cloudwatch_event_target" "securityhub_to_ingest" {
  rule      = aws_cloudwatch_event_rule.securityhub_imported.name
  target_id = "ingest"
  arn       = aws_lambda_function.ingest.arn
}

resource "aws_lambda_permission" "eventbridge_ingest" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.securityhub_imported.arn
}
