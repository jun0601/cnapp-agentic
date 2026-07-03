# =============================================================================
# infra/backend — 분석 백엔드 평면 (레이어드: shared 다음, 나머지와 병렬)
# project-draft §4.6 · console-app-design §9·§6 · §17(HITL)
#
# ★ 원래 infra/pipeline + infra/engine 두 레이어를 하나로 합친 것(2026-07-03).
#   "데이터 평면(수집·정규화)"과 "추론 평면(상관·오케스트레이터·조치)"은 둘 다
#   shared만 참조하는 백엔드 Lambda 뭉치라, 레이어를 나눌 실익보다 단순함이 큼.
#   코드 폴더(pipeline/·engine/·attackpath/)는 그대로 — 이건 '배포 껍데기'만 합친 것.
#
# 전체 흐름(2-pass, console-app-design §14):
#   [스캐너 findings] → EventBridge → ingest Lambda → SQS
#     → normalize Lambda(SQS 소비) → OCSF-lite 정규화 → RDS(pgvector)
#     → PutEvents(cnapp.findings.batch.completed)
#     → 상관 Lambda(attackpath): R1~R5 → attack-path 그래프 upsert(RDS)
#     → PutEvents(cnapp.attackpath.correlation.completed)
#     → 오케스트레이터 Lambda: Triage→Hypothesis→Evidence(Bedrock tool-use)→Reasoning
#        → case(계약⑦) upsert(RDS)
#
# 조치(HITL, §17): 콘솔 approver 승인 → console-backend가 remediation SFn StartExecution
#     → 검증 → remediation Lambda(격상 역할, 변경 API) → 불변 감사(S3 Object Lock)
#
# ⚠️ 모든 Lambda 패키지 = '배포 가능한 스텁'(index.handler). 실 apply/CI에서
#    각 코드(pipeline/·attackpath/·engine/ handler.py + psycopg2 레이어)로 교체
#    (swap 포인트 = archive_file.source). 로직은 run_e2e/run_real로 로컬 검증됨.
#
# 구역: [TF·BACKEND][PROVIDER][SHARED refs][공통 IAM·SG]
#       [데이터 평면: SQS·ingest·normalize·EventBridge]
#       [추론 평면: correlation·orchestrator·2-pass EventBridge]
#       [조치(HITL): 감사 S3·remediation Lambda·Step Functions]
# =============================================================================

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.95" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
  }
  backend "s3" {
    bucket       = "cnapp-agentic-tfstate"
    key          = "infra/backend/terraform.tfstate"
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
      Layer     = "backend"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# infra/shared 출력 참조(VPC·private subnet·RDS·엔진 IAM 정책 2종)
data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket = var.tfstate_bucket
    key    = "infra/shared/terraform.tfstate"
    region = var.region
  }
}

locals {
  vpc_id                       = data.terraform_remote_state.shared.outputs.vpc_id
  private_subnets              = data.terraform_remote_state.shared.outputs.private_subnet_ids
  rds_secret_arn               = data.terraform_remote_state.shared.outputs.rds_secret_arn
  rds_endpoint                 = data.terraform_remote_state.shared.outputs.rds_endpoint
  evidence_readonly_policy_arn = data.terraform_remote_state.shared.outputs.evidence_readonly_policy_arn
  bedrock_invoke_policy_arn    = data.terraform_remote_state.shared.outputs.bedrock_invoke_policy_arn
  account_id                   = data.aws_caller_identity.current.account_id
}

# =============================================================================
# [공통 IAM·SG] Lambda assume + 모든 백엔드 Lambda가 공유하는 egress SG
#   (pipeline·engine 시절 SG 2개가 동일 egress-all이라 하나로 통합)
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

# 모든 VPC 배치 Lambda(normalize·correlation·orchestrator·remediation)의 공용 egress SG
resource "aws_security_group" "lambda" {
  name        = "${var.project}-backend-lambda"
  description = "backend Lambda egress (normalize/correlation/orchestrator/remediation)"
  vpc_id      = local.vpc_id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # destroy 시 Lambda Hyperplane ENI가 함수 삭제 후에도 10~20분 SG를 붙잡음(AWS 플랫폼 동작,
  # 2026-07-03 라이브 destroy 실측: normalize ENI 2개가 in-use 유지). 기본 delete timeout 15분이면
  # 한 번 실패 후 재실행이 필요해져서, 원샷 destroy 되도록 대기를 늘림.
  timeouts { delete = "40m" }
}

# 상관/오케스트레이터/조치 역할 공통 베이스(로그 + RDS secret + PutEvents)
data "aws_iam_policy_document" "base" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${local.account_id}:*"]
  }
  statement {
    sid       = "ReadDbSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.rds_secret_arn]
  }
  statement {
    sid       = "EmitEvents"
    actions   = ["events:PutEvents"]
    resources = ["arn:aws:events:${var.region}:${local.account_id}:event-bus/default"]
  }
}

# =============================================================================
# ▓▓▓ 데이터 평면 (구 infra/pipeline) ▓▓▓
# 흐름: EventBridge(Security Hub Imported) → ingest Lambda → SQS → normalize Lambda
# =============================================================================

# --- [SQS] ingest → normalize 버퍼(재시도·백프레셔) + DLQ ---
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

# --- [IAM] ingest 역할: 로그 + SQS 송신(EventBridge가 호출) ---
resource "aws_iam_role" "ingest" {
  name               = "${var.project}-pipeline-ingest"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "ingest" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${local.account_id}:*"]
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

# --- [IAM] normalize 역할: 로그 + SQS 소비 + Secrets(RDS) + VPC + PutEvents ---
resource "aws_iam_role" "normalize" {
  name               = "${var.project}-pipeline-normalize"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "normalize_vpc" {
  role       = aws_iam_role.normalize.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "normalize" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${local.account_id}:*"]
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
    resources = ["arn:aws:events:${var.region}:${local.account_id}:event-bus/default"]
  }
}

resource "aws_iam_role_policy" "normalize" {
  name   = "normalize"
  role   = aws_iam_role.normalize.id
  policy = data.aws_iam_policy_document.normalize.json
}

# --- [LAMBDA] ingest·normalize (배포 가능 스텁 · 실코드 스왑 포인트) ---
data "archive_file" "ingest" {
  type        = "zip"
  output_path = "${path.module}/build/ingest.zip"
  source {
    filename = "index.py"
    content  = <<-PY
      # 실코드 스왑 = handler "pipeline.ingest.handler.handler"(pipeline 패키지 번들, boto3만/RDS 불요).
      # 지금은 배포 가능한 스텁(이벤트 로깅). 실코드는 pipeline/ingest/handler.py에 있음.
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
      # 실코드 스왑 = handler "pipeline.normalize.handler.handler"(pipeline 패키지 + psycopg2 레이어).
      # findings 테이블 필요 → 스키마 infra/shared/db/schema.sql 선적용. 실코드는 pipeline/normalize/handler.py.
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

# --- [EVENTBRIDGE] Security Hub Findings Imported(기본 버스) → ingest Lambda ---
#   (Prowler S3 드롭·커스텀 소스는 ingest가 S3 이벤트로도 받음 — pipeline/ingest 참조)
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

# =============================================================================
# ▓▓▓ 추론 평면 (구 infra/engine 분석부) ▓▓▓
# 2-pass: batch.completed → correlation(attackpath) → correlation.completed → orchestrator
# =============================================================================

# --- 상관 Lambda 역할(attackpath) ---
resource "aws_iam_role" "correlation" {
  name               = "${var.project}-engine-correlation"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
resource "aws_iam_role_policy" "correlation" {
  name   = "base"
  role   = aws_iam_role.correlation.id
  policy = data.aws_iam_policy_document.base.json
}
resource "aws_iam_role_policy_attachment" "correlation_vpc" {
  role       = aws_iam_role.correlation.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# --- 오케스트레이터 Lambda 역할(Evidence tool-use + Bedrock) ---
resource "aws_iam_role" "orchestrator" {
  name               = "${var.project}-engine-orchestrator"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
resource "aws_iam_role_policy" "orchestrator" {
  name   = "base"
  role   = aws_iam_role.orchestrator.id
  policy = data.aws_iam_policy_document.base.json
}
resource "aws_iam_role_policy_attachment" "orchestrator_vpc" {
  role       = aws_iam_role.orchestrator.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}
# Evidence read-only allowlist(계약④) + Bedrock invoke — shared에서 만든 정책 재사용
resource "aws_iam_role_policy_attachment" "orchestrator_evidence" {
  role       = aws_iam_role.orchestrator.name
  policy_arn = local.evidence_readonly_policy_arn
}
resource "aws_iam_role_policy_attachment" "orchestrator_bedrock" {
  role       = aws_iam_role.orchestrator.name
  policy_arn = local.bedrock_invoke_policy_arn
}

# --- [LAMBDA 분석] 상관 + 오케스트레이터 (배포 가능 스텁 · 실코드 스왑 포인트) ---
data "archive_file" "correlation" {
  type        = "zip"
  output_path = "${path.module}/build/correlation.zip"
  source {
    filename = "index.py"
    content  = <<-PY
      # 실코드 스왑 = handler "attackpath.correlation.handler.handler"(attackpath 패키지 + psycopg2).
      # findings/attack_paths 테이블 필요 → 스키마 infra/shared/db/schema.sql. 실코드=attackpath/correlation/handler.py.
      import json
      def handler(event, context):
          print("correlation:", json.dumps(event)[:500])
          return {"ok": True}
    PY
  }
}

data "archive_file" "orchestrator" {
  type        = "zip"
  output_path = "${path.module}/build/orchestrator.zip"
  source {
    filename = "index.py"
    content  = <<-PY
      # 실코드 스왑 = handler "engine.handler.handler"(engine 패키지 + psycopg2, REAL_TOOLS=1이면 실 Bedrock tool-use).
      # cases/findings 테이블 필요 → 스키마 infra/shared/db/schema.sql. 실코드=engine/handler.py(run_real.py 구성 미러링).
      import json
      def handler(event, context):
          print("orchestrator:", json.dumps(event)[:500])
          return {"ok": True}
    PY
  }
}

resource "aws_cloudwatch_log_group" "correlation" {
  name              = "/aws/lambda/${var.project}-correlation"
  retention_in_days = var.log_retention_days
}
resource "aws_cloudwatch_log_group" "orchestrator" {
  name              = "/aws/lambda/${var.project}-orchestrator"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "correlation" {
  function_name    = "${var.project}-correlation"
  role             = aws_iam_role.correlation.arn
  runtime          = "python3.12"
  handler          = "index.handler"
  filename         = data.archive_file.correlation.output_path
  source_code_hash = data.archive_file.correlation.output_base64sha256
  timeout          = 120
  memory_size      = 512
  vpc_config {
    subnet_ids         = local.private_subnets
    security_group_ids = [aws_security_group.lambda.id]
  }
  environment {
    variables = { DB_HOST = local.rds_endpoint, DB_SECRET_ARN = local.rds_secret_arn }
  }
  depends_on = [aws_cloudwatch_log_group.correlation, aws_iam_role_policy_attachment.correlation_vpc]
}

resource "aws_lambda_function" "orchestrator" {
  function_name    = "${var.project}-orchestrator"
  role             = aws_iam_role.orchestrator.arn
  runtime          = "python3.12"
  handler          = "index.handler"
  filename         = data.archive_file.orchestrator.output_path
  source_code_hash = data.archive_file.orchestrator.output_base64sha256
  timeout          = 300 # Evidence tool-use 루프(Bedrock 왕복) 여유
  memory_size      = 1024
  vpc_config {
    subnet_ids         = local.private_subnets
    security_group_ids = [aws_security_group.lambda.id]
  }
  environment {
    variables = {
      DB_HOST       = local.rds_endpoint
      DB_SECRET_ARN = local.rds_secret_arn
      # 실 tool-use model ID(manual-infra §4) — Global inference profile
      BEDROCK_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
    }
  }
  depends_on = [aws_cloudwatch_log_group.orchestrator, aws_iam_role_policy_attachment.orchestrator_vpc]
}

# --- [EVENTBRIDGE] 2-pass 트리거 체인 (기본 버스) ---
#   ① cnapp.findings.batch.completed → correlation
#   ② cnapp.attackpath.correlation.completed → orchestrator
resource "aws_cloudwatch_event_rule" "batch_completed" {
  name        = "${var.project}-batch-completed"
  description = "정규화 배치 완료 → 상관"
  event_pattern = jsonencode({
    source        = ["cnapp.findings"]
    "detail-type" = ["cnapp.findings.batch.completed"]
  })
}
resource "aws_cloudwatch_event_target" "batch_to_correlation" {
  rule      = aws_cloudwatch_event_rule.batch_completed.name
  target_id = "correlation"
  arn       = aws_lambda_function.correlation.arn
}
resource "aws_lambda_permission" "eb_correlation" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.correlation.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.batch_completed.arn
}

resource "aws_cloudwatch_event_rule" "correlation_completed" {
  name        = "${var.project}-correlation-completed"
  description = "attack-path 상관 완료 → 오케스트레이터(능동조사)"
  event_pattern = jsonencode({
    source        = ["cnapp.attackpath"]
    "detail-type" = ["cnapp.attackpath.correlation.completed"]
  })
}
resource "aws_cloudwatch_event_target" "corr_to_orchestrator" {
  rule      = aws_cloudwatch_event_rule.correlation_completed.name
  target_id = "orchestrator"
  arn       = aws_lambda_function.orchestrator.arn
}
resource "aws_lambda_permission" "eb_orchestrator" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.orchestrator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.correlation_completed.arn
}

# =============================================================================
# ▓▓▓ 조치 (HITL — 구 infra/engine 조치부) ▓▓▓
#   콘솔 approver 승인 → console-backend가 remediation SFn StartExecution
#   MVP 카탈로그 3종(project-draft §24): S3 public block · SG 0.0.0.0 제거 · IAM diff
#   ⚠️ 격상 역할(변경 API)은 이 경로에서만 — 콘솔/분석 역할은 read-only(§17)
# =============================================================================

# [AUDIT] 불변 감사 로그 — S3 Object Lock. 조치 실행기가 조치 레코드를 여기에 저장(§17, 사후 변조 불가).
resource "aws_s3_bucket" "audit" {
  bucket              = "${var.project}-audit-${local.account_id}"
  object_lock_enabled = true
  force_destroy       = true # 데모 편의. ⚠️ 보존기간 내 객체는 잠겨 destroy 실패 가능(GOVERNANCE 우회 필요)
}
resource "aws_s3_bucket_versioning" "audit" {
  bucket = aws_s3_bucket.audit.id
  versioning_configuration { status = "Enabled" } # Object Lock 전제
}
resource "aws_s3_bucket_object_lock_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    default_retention {
      mode = "GOVERNANCE" # 데모(특권 우회 가능). 운영이면 COMPLIANCE(우회 불가)
      days = 1
    }
  }
}
resource "aws_s3_bucket_public_access_block" "audit" {
  bucket                  = aws_s3_bucket.audit.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_iam_role" "remediation_lambda" {
  name               = "${var.project}-remediation-executor"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# 격상 권한: 조치 3종에 필요한 '변경' API만. TODO(실 apply): 리소스 스코프 좁히기.
data "aws_iam_policy_document" "remediation" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${local.account_id}:*"]
  }
  # 조치 3종을 '타깃(shop) 리소스'로 스코프 — 특히 iam:PutRolePolicy를 임의 역할(admin 포함) 재작성 못 하게 제한(권한상승 차단).
  statement {
    sid       = "RemediateS3"
    actions   = ["s3:PutBucketPublicAccessBlock", "s3:PutBucketPolicy"]
    resources = ["arn:aws:s3:::${var.project}-*", "arn:aws:s3:::member-pii-*"] # 타깃 버킷만
  }
  statement {
    sid       = "RemediateSG"
    actions   = ["ec2:RevokeSecurityGroupIngress"]
    resources = ["arn:aws:ec2:${var.region}:${local.account_id}:security-group/*"]
    # 진우 판단필요(c) 반영: Layer=target 태그 SG로만 제한 → 잘못된 SG ID로 RDS/NAT/ALB SG를 건드릴
    # 가용성 리스크 차단. 태그 조건이라 infra/target remote_state 결합 없이 좁힘(apply 순서 무영향).
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Layer"
      values   = ["target"]
    }
  }
  statement {
    sid       = "RemediateIAM"
    actions   = ["iam:GetRolePolicy", "iam:PutRolePolicy"]
    resources = ["arn:aws:iam::${local.account_id}:role/${var.project}-target-*"] # 타깃 IRSA 역할만 — admin 재작성 차단
  }
  statement {
    sid       = "AuditWrite" # 불변 감사 기록(Object Lock 버킷)
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.audit.arn}/*"]
  }
  statement {
    sid       = "ReadDbSecret" # RDS 상태 갱신용(수정→소멸 루프)
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.rds_secret_arn]
  }
}
resource "aws_iam_role_policy" "remediation" {
  name   = "remediation"
  role   = aws_iam_role.remediation_lambda.id
  policy = data.aws_iam_policy_document.remediation.json
}
# RDS(VPC) 접근용 ENI 관리
resource "aws_iam_role_policy_attachment" "remediation_vpc" {
  role       = aws_iam_role.remediation_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "archive_file" "remediation" {
  type        = "zip"
  output_path = "${path.module}/build/remediation.zip"
  source {
    filename = "index.py"
    content  = <<-PY
      # 실코드 스왑 = handler "engine.remediation.handler"(engine 패키지 + psycopg2 레이어).
      # 실코드는 engine/remediation.py(S3 block·SG revoke·IAM diff → dry-run/apply → 감사·RDS). 지금은 스텁.
      import json
      def handler(event, context):
          print("remediation:", json.dumps(event)[:500])
          return {"ok": True, "applied": False}  # 스텁은 실제 변경 안 함
    PY
  }
}

resource "aws_cloudwatch_log_group" "remediation" {
  name              = "/aws/lambda/${var.project}-remediation"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "remediation" {
  function_name    = "${var.project}-remediation"
  role             = aws_iam_role.remediation_lambda.arn
  runtime          = "python3.12"
  handler          = "index.handler"
  filename         = data.archive_file.remediation.output_path
  source_code_hash = data.archive_file.remediation.output_base64sha256
  timeout          = 120
  memory_size      = 256
  # RDS 상태 갱신(수정→소멸 루프) 위해 VPC 배치. S3/EC2/IAM 변경 API는 NAT로 egress.
  vpc_config {
    subnet_ids         = local.private_subnets
    security_group_ids = [aws_security_group.lambda.id]
  }
  environment {
    variables = {
      AUDIT_BUCKET  = aws_s3_bucket.audit.bucket
      DB_HOST       = local.rds_endpoint
      DB_SECRET_ARN = local.rds_secret_arn
    }
  }
  depends_on = [aws_cloudwatch_log_group.remediation, aws_iam_role_policy_attachment.remediation_vpc]
}

# Step Functions 실행 역할(remediation Lambda 호출)
data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}
resource "aws_iam_role" "sfn" {
  name               = "${var.project}-remediation-sfn"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}
resource "aws_iam_role_policy" "sfn" {
  name = "invoke-remediation"
  role = aws_iam_role.sfn.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = [aws_lambda_function.remediation.arn]
    }]
  })
}

resource "aws_sfn_state_machine" "remediation" {
  name     = "${var.project}-remediation"
  role_arn = aws_iam_role.sfn.arn
  definition = jsonencode({
    Comment = "HITL 조치(승인 후): 검증 → 적용(engine/remediation.py: dry-run/apply + Object Lock 감사 + RDS 수정→소멸) → 완료"
    StartAt = "ValidateApproval"
    States = {
      ValidateApproval = {
        Type    = "Pass"
        Comment = "approver 승인 사실은 console-backend가 이미 확인(403 게이트) — 여기선 payload 검증만"
        Next    = "ApplyFix"
      }
      ApplyFix = {
        Type       = "Task"
        Resource   = aws_lambda_function.remediation.arn
        Next       = "RecordAudit"
        Retry      = [{ ErrorEquals = ["States.ALL"], MaxAttempts = 2, IntervalSeconds = 5 }]
        Catch      = [{ ErrorEquals = ["States.ALL"], Next = "Failed" }]
        ResultPath = "$.result"
      }
      RecordAudit = {
        Type    = "Pass"
        Comment = "감사(Object Lock)·RDS 상태 갱신은 ApplyFix(engine/remediation.py)가 수행 — 여기선 완료 마킹"
        End     = true
      }
      Failed = { Type = "Fail", Cause = "remediation failed" }
    }
  })
}
