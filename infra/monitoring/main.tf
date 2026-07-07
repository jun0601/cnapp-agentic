# =============================================================================
# infra/monitoring — 운영 관측(진우 담당, 레이어드: shared 다음, console/pipeline/engine 이후)
# CLAUDE §5 "모니터링·관제·추적(Grafana·CloudTrail)" 코드화. 설계 근거는 README.md(§1~11).
#
# 이 레이어가 만드는 것:
#   ① Grafana IRSA 역할 — CloudWatch를 데이터소스로 붙일 때 필요한 read-only 권한.
#      Prometheus(kube-prometheus-stack, gitops/monitoring/)는 EKS 안의 것만 보므로,
#      Lambda·RDS·SQS·ALB·SFn·S3·Bedrock·Cognito(EKS 밖)는 Grafana의 CloudWatch 데이터소스로 통합.
#   ② CloudWatch Dashboard — ①②③ 3개 관측 축(README §1)을 한 화면에(코드로 관리).
#   ③ CloudTrail → CloudWatch Logs 배관(트레일 자체는 수동 유지, README §10).
#   ④ Teams 알림(SNS → Lambda → Power Automate webhook, README §11).
#
# ⚠️ Prometheus 자체(노드/파드 인프라 메트릭)는 IRSA 불필요 — K8s API·파드 네트워크만 씀.
#    IRSA는 오직 "Grafana가 CloudWatch를 추가로 읽고 싶을 때"만 필요.
#
# 구역: [TF·BACKEND] [PROVIDER] [REMOTE STATE] [IRSA] [DASHBOARD] [CLOUDTRAIL] [TEAMS 알림] [알람]
# =============================================================================

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.95" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
  }
  backend "s3" {
    bucket       = "cnapp-agentic-tfstate"
    key          = "infra/monitoring/terraform.tfstate"
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
      Layer     = "monitoring"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# --- 다른 레이어 출력 참조(전부 읽기 전용 data source, 이 레이어가 만들지 않음) ---
data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket = var.tfstate_bucket
    key    = "infra/shared/terraform.tfstate"
    region = var.region
  }
}

data "terraform_remote_state" "console" {
  backend = "s3"
  config = {
    bucket = var.tfstate_bucket
    key    = "infra/console/terraform.tfstate"
    region = var.region
  }
}

data "terraform_remote_state" "backend" {
  backend = "s3"
  config = {
    bucket = var.tfstate_bucket
    key    = "infra/backend/terraform.tfstate"
    region = var.region
  }
}

locals {
  oidc_provider_arn = data.terraform_remote_state.shared.outputs.eks_oidc_provider_arn
  oidc_provider     = data.terraform_remote_state.shared.outputs.eks_oidc_provider

  # 이름은 각 레이어의 명명 규칙("${var.project}-...")을 재구성(레이어 간 이미 확립된 패턴).
  rds_identifier       = "${var.project}-pgvector"
  sqs_ingest_name      = "${var.project}-ingest"
  sqs_ingest_dlq       = "${var.project}-ingest-dlq"
  alb_arn_suffix       = data.terraform_remote_state.console.outputs.alb_arn_suffix
  cognito_user_pool_id = data.terraform_remote_state.console.outputs.cognito_user_pool_id
  # 2026-07-03: infra/console에 output 추가됨(진우 요청 → 준형 반영) — 더는 변수 게이트 불필요,
  # 레이어 순서(console이 monitoring보다 항상 먼저 apply)상 이 값은 항상 존재함.
  cloudfront_distribution_id = data.terraform_remote_state.console.outputs.cloudfront_distribution_id

  # 계정ID가 이름에 붙어 재구성이 안 되는 리소스 2종은 backend의 실제 output을 그대로 참조.
  remediation_sfn_arn = data.terraform_remote_state.backend.outputs.remediation_state_machine_arn
  audit_bucket_name   = data.terraform_remote_state.backend.outputs.audit_bucket

  # Lambda 6종(2026-07-02 조치 실행기 추가로 5→6). 새 Lambda 추가 시 여기만 늘리면
  # 대시보드 위젯·에러 알람(for_each) 둘 다 자동 반영됨(스켈레톤 목적).
  lambda_names = [
    "${var.project}-ingest",
    "${var.project}-normalize",
    "${var.project}-correlation",
    "${var.project}-orchestrator",
    "${var.project}-console-backend",
    "${var.project}-remediation",
  ]

  # Bedrock 모델별 위젯용. Reasoning/Hypothesis/RAG가 아직 mock이라 지금은 Haiku만 실사용.
  # Sonnet 실전환 시 이 리스트에 추가하면 위젯·비용 계산이 자동으로 모델별로 갈라짐.
  bedrock_model_ids = [
    "global.anthropic.claude-haiku-4-5-20251001-v1:0", # Evidence(실사용, Phase1 실증 완료)
  ]

  # Bedrock 모델별 위젯(y=42부터 모델당 1행=6 차지)이 끝나는 y좌표 — 아래 비용/EMF/CloudFront
  # 위젯이 전부 이 값 기준으로 이어 붙는다. bedrock_model_ids에 모델을 추가해도(예: Sonnet)
  # 레이아웃이 자동으로 밀려서 겹치지 않는다(하드코딩 y였을 때의 겹침 버그 방지).
  bedrock_rows_end_y = 42 + length(local.bedrock_model_ids) * 6
}

# =============================================================================
# [IAM] Lambda 공용 assume-role 문서(Teams notifier가 사용)
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

# =============================================================================
# [IRSA] Grafana ServiceAccount → CloudWatch read-only
#   trust policy: OIDC federated, sub 조건 = 이 네임스페이스·SA로 뜬 파드만 assume 가능
# =============================================================================
data "aws_iam_policy_document" "grafana_irsa_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"
    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider}:sub"
      values   = ["system:serviceaccount:${var.grafana_namespace}:${var.grafana_service_account}"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "grafana" {
  name               = "${var.project}-monitoring-grafana-irsa"
  assume_role_policy = data.aws_iam_policy_document.grafana_irsa_trust.json
}

# Grafana CloudWatch 데이터소스 공식 권장 최소 권한(https://grafana.com/docs/grafana/latest/datasources/aws-cloudwatch/) — read-only.
# 참고: cloudwatch:* 읽기 액션은 리소스 레벨 권한을 지원하지 않아 Resource="*"가 AWS 표준(네임스페이스
# 무관하게 전부 커버) — 이 정책 그대로 AWS/States·AWS/S3·AWS/Cognito·AWS/Bedrock·AWS/CloudFront까지
# 추가 변경 없이 읽을 수 있음.
data "aws_iam_policy_document" "grafana_cloudwatch" {
  statement {
    sid = "CloudWatchReadOnly"
    actions = [
      "cloudwatch:DescribeAlarmsForMetric",
      "cloudwatch:DescribeAlarmHistory",
      "cloudwatch:DescribeAlarms",
      "cloudwatch:ListMetrics",
      "cloudwatch:GetMetricData",
      "cloudwatch:GetMetricStatistics",
      "cloudwatch:GetInsightRuleReport",
    ]
    resources = ["*"]
  }
  statement {
    sid = "LogsReadOnly"
    actions = [
      "logs:DescribeLogGroups",
      "logs:GetLogGroupFields",
      "logs:StartQuery",
      "logs:StopQuery",
      "logs:GetQueryResults",
      "logs:GetLogEvents",
    ]
    resources = ["*"]
  }
  statement {
    sid       = "TagsForDiscovery"
    actions   = ["ec2:DescribeTags", "ec2:DescribeInstances", "ec2:DescribeRegions", "tag:GetResources"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "grafana_cloudwatch" {
  name   = "cloudwatch-readonly"
  role   = aws_iam_role.grafana.id
  policy = data.aws_iam_policy_document.grafana_cloudwatch.json
}

# =============================================================================
# [ALB CONTROLLER] AWS Load Balancer Controller IRSA — Grafana를 도메인으로 노출하는 데 필요
#   (2026-07-07 추가). Karpenter 노드는 ASG가 아니라서 NodePort+수동 Target Group 등록이
#   안 통함 — 이 컨트롤러가 파드 IP를 직접 Target Group에 등록(IP 모드)해서 노드가 계속
#   바뀌어도 문제없음. K8s Ingress 하나로 ALB를 선언적으로 관리(현업 표준 패턴).
#   IAM 정책은 공식 문서 그대로(iam/aws-load-balancer-controller-policy.json).
# =============================================================================
data "aws_iam_policy_document" "alb_controller_irsa_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"
    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider}:sub"
      values   = ["system:serviceaccount:kube-system:aws-load-balancer-controller"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "alb_controller" {
  name               = "${var.project}-alb-controller-irsa"
  assume_role_policy = data.aws_iam_policy_document.alb_controller_irsa_trust.json
}

resource "aws_iam_policy" "alb_controller" {
  name   = "${var.project}-alb-controller-policy"
  policy = file("${path.module}/iam/aws-load-balancer-controller-policy.json")
}

resource "aws_iam_role_policy_attachment" "alb_controller" {
  role       = aws_iam_role.alb_controller.name
  policy_arn = aws_iam_policy.alb_controller.arn
}

# =============================================================================
# [DASHBOARD] CloudWatch Dashboard — EKS 밖(①②③ 전 축) 한 화면
#   Prometheus/Grafana(EKS 안)와 상호보완 — 이 대시보드는 콘솔에서도 바로 보임(Grafana 없이도 유효).
#
#   레이아웃(2열 그리드, 행당 height=6) — 위젯 추가 시 다음 y만 이어서 쓰면 됨:
#     y=0~18            : Lambda 6종(3행, 자동 배치)
#     y=18              : SQS 큐 깊이/DLQ         | RDS CPU/연결수
#     y=24              : ALB                    | SQS 백로그 나이(오래된 메시지)
#     y=30              : RDS 스토리지/IOPS       | Step Functions(remediation HITL)
#     y=36              : S3 감사버킷(Object Lock)| Cognito 로그인
#     y=42~bedrock_rows_end_y : Bedrock 호출/지연 | Bedrock 에러/토큰 (모델 1개당 1행 — local.bedrock_rows_end_y로 자동 계산)
#     y=bedrock_rows_end_y    : Bedrock 추정비용(전체폭)
#     y=bedrock_rows_end_y+6  : 엔진 트리아지 게이트 | 엔진 tool-use/확신도
#     y=bedrock_rows_end_y+12 : 엔진 판정까지 시간   | 엔진 판정 분포(Verdict×RiskLevel)
#     y=bedrock_rows_end_y+18 : CloudFront 요청수/에러율(infra/console output, 2026-07-03 게이트 해제)
#   ⚠️ bedrock_model_ids에 모델을 추가하면(Sonnet 등) 이 아래 전부가 자동으로 밀려서 겹치지 않음 —
#      과거엔 y를 하드코딩해서 모델 2개가 되면 비용/EMF 위젯과 겹치는 버그가 있었음(2026-07-03 수정).
# =============================================================================
resource "aws_cloudwatch_dashboard" "platform" {
  dashboard_name = "${var.project}-platform"
  dashboard_body = jsonencode({
    widgets = concat(
      # --- Lambda 6종(2열 자동배치, y=0~18) ---
      [
        for i, fn in local.lambda_names : {
          type   = "metric"
          x      = (i % 2) * 12
          y      = floor(i / 2) * 6
          width  = 12
          height = 6
          properties = {
            title  = "Lambda: ${fn}"
            region = var.region
            metrics = [
              ["AWS/Lambda", "Invocations", "FunctionName", fn, { stat = "Sum" }],
              [".", "Errors", ".", ".", { stat = "Sum" }],
              [".", "Duration", ".", ".", { stat = "Average" }],
              [".", "Throttles", ".", ".", { stat = "Sum" }],
            ]
            period = 300
          }
        }
      ],
      # --- 축①②: 인프라 전체 (y=18~48) ---
      [
        {
          type = "metric", x = 0, y = 18, width = 12, height = 6
          properties = {
            title  = "SQS: ingest 큐 깊이 / DLQ 적재"
            region = var.region
            metrics = [
              ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", local.sqs_ingest_name],
              ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", local.sqs_ingest_dlq, { color = "#d62728" }],
            ]
            period = 300
          }
        },
        {
          type = "metric", x = 12, y = 18, width = 12, height = 6
          properties = {
            title  = "RDS: CPU / 연결 수 (${local.rds_identifier})"
            region = var.region
            metrics = [
              ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", local.rds_identifier],
              [".", "DatabaseConnections", ".", ".", { yAxis = "right" }],
            ]
            period = 300
          }
        },
        {
          type = "metric", x = 0, y = 24, width = 12, height = 6
          properties = {
            title  = "ALB: 요청 수 / 지연시간 / 5xx"
            region = var.region
            metrics = [
              ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", local.alb_arn_suffix, { stat = "Sum" }],
              [".", "TargetResponseTime", ".", ".", { stat = "Average", yAxis = "right" }],
              [".", "HTTPCode_Target_5XX_Count", ".", ".", { stat = "Sum", color = "#d62728" }],
            ]
            period = 300
          }
        },
        {
          type = "metric", x = 12, y = 24, width = 12, height = 6
          properties = {
            title  = "SQS: ingest 백로그 나이(오래된 메시지, 지연 체감)"
            region = var.region
            metrics = [
              ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", local.sqs_ingest_name, { stat = "Maximum" }],
            ]
            period = 300
          }
        },
        {
          type = "metric", x = 0, y = 30, width = 12, height = 6
          properties = {
            title  = "RDS: 여유 스토리지 / 읽기 IOPS"
            region = var.region
            metrics = [
              ["AWS/RDS", "FreeStorageSpace", "DBInstanceIdentifier", local.rds_identifier],
              [".", "ReadIOPS", ".", ".", { yAxis = "right" }],
            ]
            period = 300
          }
        },
        {
          type = "metric", x = 12, y = 30, width = 12, height = 6
          properties = {
            title  = "Step Functions: remediation(HITL) 실행 결과"
            region = var.region
            metrics = [
              ["AWS/States", "ExecutionsSucceeded", "StateMachineArn", local.remediation_sfn_arn, { stat = "Sum" }],
              [".", "ExecutionsFailed", ".", ".", { stat = "Sum", color = "#d62728" }],
              [".", "ExecutionsAborted", ".", ".", { stat = "Sum", color = "#ff9896" }],
              [".", "ExecutionTime", ".", ".", { stat = "Average", yAxis = "right" }],
            ]
            period = 300
          }
        },
        {
          # S3 스토리지 지표는 하루 1회만 발행 — period를 86400(1일)로.
          type = "metric", x = 0, y = 36, width = 12, height = 6
          properties = {
            title  = "S3: 감사 버킷(Object Lock) 크기/객체 수 — 조치 몇 건 쌓였나"
            region = var.region
            metrics = [
              ["AWS/S3", "NumberOfObjects", "BucketName", local.audit_bucket_name, "StorageType", "AllStorageTypes", { stat = "Average" }],
              [".", "BucketSizeBytes", ".", ".", "StorageType", "StandardStorage", { stat = "Average", yAxis = "right" }],
            ]
            period = 86400
          }
        },
        {
          # 참고: 기본(비-Advanced Security) User Pool엔 실패 카운터가 따로 없어 성공 지표만 노출.
          type = "metric", x = 12, y = 36, width = 12, height = 6
          properties = {
            title  = "Cognito: 로그인 성공 (콘솔 SSO)"
            region = var.region
            metrics = [
              ["AWS/Cognito", "SignInSuccesses", "UserPool", local.cognito_user_pool_id, { stat = "Sum" }],
            ]
            period = 300
          }
        },
      ],
      # --- 축③ 1단: Bedrock native(코드 계측 불요, 모델별) — y=42~54 ---
      [
        for j, model_id in local.bedrock_model_ids : {
          type = "metric", x = 0, y = 42 + j * 6, width = 12, height = 6
          properties = {
            title  = "Bedrock 호출/지연 (${model_id})"
            region = var.region
            metrics = [
              ["AWS/Bedrock", "Invocations", "ModelId", model_id, { stat = "Sum" }],
              [".", "InvocationLatency", ".", ".", { stat = "Average", yAxis = "right" }],
            ]
            period = 300
          }
        }
      ],
      [
        for j, model_id in local.bedrock_model_ids : {
          type = "metric", x = 12, y = 42 + j * 6, width = 12, height = 6
          properties = {
            title  = "Bedrock 에러/토큰 사용량 (${model_id})"
            region = var.region
            metrics = [
              ["AWS/Bedrock", "InvocationClientErrors", "ModelId", model_id, { stat = "Sum", color = "#d62728" }],
              [".", "InvocationServerErrors", ".", ".", { stat = "Sum", color = "#ff9896" }],
              [".", "InputTokenCount", ".", ".", { stat = "Sum", yAxis = "right" }],
              [".", "OutputTokenCount", ".", ".", { stat = "Sum", yAxis = "right" }],
            ]
            period = 300
          }
        }
      ],
      [
        {
          # 단가는 variables.tf(bedrock_*_price_*)로 변수화 — 가격 바뀌면 위젯이 아니라 변수만 갱신.
          # metric math m1/m2 라벨은 dashboard 표시용이라 실제 계산엔 안 쓰임(id만 참조됨).
          type = "metric", x = 0, y = local.bedrock_rows_end_y, width = 24, height = 6
          properties = {
            title  = "Bedrock 추정 비용(Haiku, USD) — metric math, 코드 계측 불요"
            region = var.region
            metrics = [
              ["AWS/Bedrock", "InputTokenCount", "ModelId", local.bedrock_model_ids[0], { id = "m1", visible = false, stat = "Sum" }],
              [".", "OutputTokenCount", ".", ".", { id = "m2", visible = false, stat = "Sum" }],
              [{ expression = "(m1/1000)*${var.bedrock_haiku_price_in_per_1k} + (m2/1000)*${var.bedrock_haiku_price_out_per_1k}", label = "Haiku 추정비용(USD)", id = "cost" }],
            ]
            period = 300
          }
        },
      ],
      # --- 축③ 2단: 에이전트 행동(EMF 커스텀, CnappAgentic/Engine) — y=bedrock_rows_end_y+6~+24 ---
      # engine/reasoning/orchestrator.py(진우 소유)의 _emit_case_metrics·_emit_tool_usage_metrics가
      # 이 네임스페이스로 EMF를 발행한다(2026-07-03 계측 완료). ⚠️ 다만 두 함수 다 Lambda 밖(로컬
      # run_demo/run_e2e)에선 미발행이라, orchestrator가 실제로 Lambda로 배포돼 실 finding을
      # 처리하기 전까지는 아래 6개 위젯이 "No data"로 보이는 게 정상(계측 부재가 아니라 미가동).
      #    _emit_case_metrics가 Dimensions=[[], ["Verdict","RiskLevel"]] 둘 다 발행하므로,
      #    총계 위젯은 무디멘션 메트릭을 직접 참조(SEARCH 불요 — 알람에서도 재사용 가능한 형태로 통일).
      #    분포(판정 분포) 위젯만 SEARCH로 Verdict×RiskLevel 조합별 세부 시계열을 펼쳐서 보여준다
      #    (SEARCH는 대시보드에선 정상 지원 — 알람에서만 금지). 케이스별 정확한 비용/사용 tool은
      #    CaseId를 지표 Dimension으로 안 두고(카디널리티 폭발 방지) CloudWatch Logs Insights로
      #    이 EMF 로그를 CaseId로 직접 검색해서 본다(README §2③.3).
      [
        {
          type = "metric", x = 0, y = local.bedrock_rows_end_y + 6, width = 12, height = 6
          properties = {
            title  = "엔진: 트리아지 게이트(findings 평가/승급, 전체 합)"
            region = var.region
            metrics = [
              ["CnappAgentic/Engine", "FindingsEvaluated", { stat = "Sum" }],
              ["CnappAgentic/Engine", "FindingsEscalated", { stat = "Sum" }],
            ]
            period = 300
          }
        },
        {
          type = "metric", x = 12, y = local.bedrock_rows_end_y + 6, width = 12, height = 6
          properties = {
            title  = "엔진: case당 tool-use 횟수 / 확신도(전체 평균)"
            region = var.region
            metrics = [
              ["CnappAgentic/Engine", "ToolCallsPerCase", { stat = "Average" }],
              ["CnappAgentic/Engine", "ConfidenceScore", { stat = "Average", yAxis = "right" }],
            ]
            period = 300
          }
        },
        {
          type = "metric", x = 0, y = local.bedrock_rows_end_y + 12, width = 12, height = 6
          properties = {
            title  = "엔진: 판정까지 걸린 시간(ms, 전체 평균)"
            region = var.region
            metrics = [
              ["CnappAgentic/Engine", "TimeToVerdictMs", { stat = "Average" }],
            ]
            period = 300
          }
        },
        {
          # 유일하게 SEARCH를 쓰는 위젯 — Verdict×RiskLevel 조합별로 선을 펼쳐 분포를 보여줌
          # (대시보드 전용 기능, 알람엔 안 씀).
          type = "metric", x = 12, y = local.bedrock_rows_end_y + 12, width = 12, height = 6
          properties = {
            title  = "엔진: 판정 분포(Verdict × RiskLevel 조합별 건수)"
            region = var.region
            metrics = [
              [{ expression = "SEARCH('{CnappAgentic/Engine,Verdict,RiskLevel} MetricName=\"FindingsEvaluated\"', 'Sum', 300)", label = "", id = "e1" }],
            ]
            period = 300
          }
        },
        {
          # 케이스별 Bedrock 토큰(비용) — 계정 전체 집계인 축③ 1단과 달리 "엔진이 조사할 때
          # 실제로 태운 토큰"만 잡음(트리아지 게이트를 통과한 케이스 한정). 정확한 건별 값은
          # CloudWatch Logs Insights로 이 네임스페이스 로그를 CaseId로 조회.
          type = "metric", x = 0, y = local.bedrock_rows_end_y + 18, width = 12, height = 6
          properties = {
            title  = "엔진: 케이스별 Bedrock 토큰 사용량(전체 합)"
            region = var.region
            metrics = [
              ["CnappAgentic/Engine", "BedrockInputTokens", { stat = "Sum" }],
              ["CnappAgentic/Engine", "BedrockOutputTokens", { stat = "Sum" }],
            ]
            period = 300
          }
        },
        {
          # tool별 breakdown — _emit_tool_usage_metrics가 Dimensions=[["Tool"]]로 발행하므로
          # SEARCH로 Tool 값별 시계열을 펼침(판정 분포 위젯과 동일 패턴).
          type = "metric", x = 12, y = local.bedrock_rows_end_y + 18, width = 12, height = 6
          properties = {
            title  = "엔진: read-only tool별 호출 횟수(어떤 API를 조사에 썼는지)"
            region = var.region
            metrics = [
              [{ expression = "SEARCH('{CnappAgentic/Engine,Tool} MetricName=\"ToolInvocations\"', 'Sum', 300)", label = "", id = "t1" }],
            ]
            period = 300
          }
        },
      ],
      # --- CloudFront(2026-07-03: infra/console output 추가로 게이트 해제, 상시 포함) ---
      [
        {
          type = "metric", x = 0, y = local.bedrock_rows_end_y + 24, width = 12, height = 6
          properties = {
            title  = "CloudFront: 요청수 / 4xx·5xx 에러율"
            region = "us-east-1" # CloudFront 지표는 엣지 위치와 무관하게 항상 us-east-1에 발행
            metrics = [
              ["AWS/CloudFront", "Requests", "DistributionId", local.cloudfront_distribution_id, "Region", "Global", { stat = "Sum" }],
              [".", "4xxErrorRate", ".", ".", ".", ".", { stat = "Average", yAxis = "right" }],
              [".", "5xxErrorRate", ".", ".", ".", ".", { stat = "Average", yAxis = "right", color = "#d62728" }],
            ]
            period = 300
          }
        }
      ]
    )
  })
}

# =============================================================================
# [CLOUDTRAIL] 기존(수동 생성) 트레일 → CloudWatch Logs 배관만 이 레이어가 관리(README §10)
#   트레일 자체(멀티리전·SSE-S3·검증ON)는 manual-infra.md §1에서 수동 유지 — 여기서 안 건드림.
#   이유: 감사 통제(트레일)는 이 레이어의 apply→destroy 사이클 바깥에 있어야 연속성이 안 끊김.
# =============================================================================
resource "aws_cloudwatch_log_group" "cloudtrail" {
  name              = "/aws/cloudtrail/${var.project}"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "cloudtrail_cwl_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "cloudtrail_cwl" {
  name               = "${var.project}-cloudtrail-to-cwl"
  assume_role_policy = data.aws_iam_policy_document.cloudtrail_cwl_trust.json
}

data "aws_iam_policy_document" "cloudtrail_cwl_write" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.cloudtrail.arn}:*"]
  }
}

resource "aws_iam_role_policy" "cloudtrail_cwl" {
  name   = "write"
  role   = aws_iam_role.cloudtrail_cwl.id
  policy = data.aws_iam_policy_document.cloudtrail_cwl_write.json
}

# =============================================================================
# [TEAMS 알림] CloudWatch Alarms → SNS → Lambda(변환) → Power Automate webhook(README §11)
#   웹훅 URL 값 자체는 Terraform이 절대 안 씀 — 로테이션 후 콘솔/CLI로 1회 수동 주입(state 무노출).
# =============================================================================
resource "aws_secretsmanager_secret" "teams_webhook" {
  name                    = "${var.project}/teams/webhook" # infra/shared RDS 시크릿("${project}/rds/master")과 동일 네이밍 컨벤션
  description             = "Power Automate Teams 웹훅 URL(cnapp-alerts 채널, CloudWatch 알람 7종). 값은 이 레이어가 아니라 로테이션 후 콘솔/CLI(aws secretsmanager put-secret-value)로 1회 수동 주입 — Terraform state에 절대 안 남김."
  recovery_window_in_days = 0 # destroy→재-apply 이름충돌 방지(infra/shared RDS 시크릿과 동일 패턴)
}

# 비용·로그인 알림은 cnapp-alerts와 다른 전용 채널로 분리(2026-07-06 사용자 요청) — 채널마다
# Power Automate 흐름 자체가 달라서(각자 다른 Teams 커넥션 URL) 시크릿도 채널별로 별도 필요.
resource "aws_secretsmanager_secret" "teams_webhook_cost" {
  name                    = "${var.project}/teams/webhook-cost"
  description             = "Power Automate Teams 웹훅 URL(cnapp-cost 채널, daily_cost_notifier 전용). 값은 로테이션 후 콘솔/CLI로 1회 수동 주입."
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret" "teams_webhook_login" {
  name                    = "${var.project}/teams/webhook-login"
  description             = "Power Automate Teams 웹훅 URL(cnapp-login 채널, login_notifier 전용). 값은 로테이션 후 콘솔/CLI로 1회 수동 주입."
  recovery_window_in_days = 0
}

resource "aws_sns_topic" "alerts" {
  name = "${var.project}-monitoring-alerts"
}

resource "aws_cloudwatch_log_group" "teams_notifier" {
  name              = "/aws/lambda/${var.project}-monitoring-teams-notifier"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "teams_notifier" {
  name               = "${var.project}-monitoring-teams-notifier"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "teams_notifier_logs" {
  role       = aws_iam_role.teams_notifier.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "teams_notifier" {
  statement {
    sid       = "ReadWebhookSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.teams_webhook.arn]
  }
}

resource "aws_iam_role_policy" "teams_notifier" {
  name   = "read-webhook-secret"
  role   = aws_iam_role.teams_notifier.id
  policy = data.aws_iam_policy_document.teams_notifier.json
}

# 실코드(스텁 아님) — SNS 메시지 파싱 → Adaptive Card 유사 포맷 → webhook POST. stdlib+boto3만 써서
# 이 레이어 밖 패키지에 의존하지 않음(pipeline/engine처럼 별도 소스 패키지가 없어 자립 구현).
data "archive_file" "teams_notifier" {
  type        = "zip"
  source_file = "${path.module}/lambda_src/teams_notifier.py"
  output_path = "${path.module}/build/teams_notifier.zip"
}

resource "aws_lambda_function" "teams_notifier" {
  function_name    = "${var.project}-monitoring-teams-notifier"
  role             = aws_iam_role.teams_notifier.arn
  runtime          = "python3.12"
  handler          = "teams_notifier.handler"
  filename         = data.archive_file.teams_notifier.output_path
  source_code_hash = data.archive_file.teams_notifier.output_base64sha256
  timeout          = 15
  memory_size      = 128
  environment {
    variables = {
      WEBHOOK_SECRET_ARN = aws_secretsmanager_secret.teams_webhook.arn
    }
  }
  depends_on = [aws_cloudwatch_log_group.teams_notifier]
}

resource "aws_lambda_permission" "sns_invoke_teams_notifier" {
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.teams_notifier.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.alerts.arn
}

resource "aws_sns_topic_subscription" "teams_notifier" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.teams_notifier.arn
}

# =============================================================================
# [일일 비용 알림] 매일 09:00 KST(=00:00 UTC) 전날 사용 비용을 Cost Explorer로 조회해 Teams 발행.
#   CloudWatch 알람이 아니라 능동 Lambda — Cost Explorer는 "임계값 초과"가 아니라 "매일 정기 리포트"
#   개념이라 알람 모델과 안 맞는다(항상 무언가는 보고할 값이 있음).
#   ⚠️ Cost Explorer API 엔드포인트는 계정 리전과 무관하게 us-east-1 고정(AWS 제약, lambda_src 주석 참고).
# =============================================================================
resource "aws_cloudwatch_log_group" "daily_cost_notifier" {
  name              = "/aws/lambda/${var.project}-monitoring-daily-cost-notifier"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "daily_cost_notifier" {
  name               = "${var.project}-monitoring-daily-cost-notifier"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "daily_cost_notifier_logs" {
  role       = aws_iam_role.daily_cost_notifier.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "daily_cost_notifier" {
  statement {
    sid       = "ReadCostExplorer"
    actions   = ["ce:GetCostAndUsage"]
    resources = ["*"] # Cost Explorer는 리소스 레벨 권한 미지원(계정 전체 대상 API)
  }
  statement {
    sid       = "ReadWebhookSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.teams_webhook_cost.arn]
  }
}

resource "aws_iam_role_policy" "daily_cost_notifier" {
  name   = "cost-explorer-and-read-webhook-secret"
  role   = aws_iam_role.daily_cost_notifier.id
  policy = data.aws_iam_policy_document.daily_cost_notifier.json
}

data "archive_file" "daily_cost_notifier" {
  type        = "zip"
  source_file = "${path.module}/lambda_src/daily_cost_notifier.py"
  output_path = "${path.module}/build/daily_cost_notifier.zip"
}

resource "aws_lambda_function" "daily_cost_notifier" {
  function_name    = "${var.project}-monitoring-daily-cost-notifier"
  role             = aws_iam_role.daily_cost_notifier.arn
  runtime          = "python3.12"
  handler          = "daily_cost_notifier.handler"
  filename         = data.archive_file.daily_cost_notifier.output_path
  source_code_hash = data.archive_file.daily_cost_notifier.output_base64sha256
  timeout          = 30
  memory_size      = 128
  environment {
    variables = {
      WEBHOOK_SECRET_ARN = aws_secretsmanager_secret.teams_webhook_cost.arn
    }
  }
  depends_on = [aws_cloudwatch_log_group.daily_cost_notifier]
}

resource "aws_cloudwatch_event_rule" "daily_cost_schedule" {
  name                = "${var.project}-monitoring-daily-cost-schedule"
  description         = "매일 09:00 KST 전날 비용 리포트(daily_cost_notifier 트리거)"
  schedule_expression = "cron(0 0 * * ? *)" # UTC 00:00 = KST 09:00
}

resource "aws_cloudwatch_event_target" "daily_cost_schedule" {
  rule = aws_cloudwatch_event_rule.daily_cost_schedule.name
  arn  = aws_lambda_function.daily_cost_notifier.arn
}

resource "aws_lambda_permission" "eventbridge_invoke_daily_cost_notifier" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.daily_cost_notifier.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_cost_schedule.arn
}

# =============================================================================
# [콘솔 로그인 알림] CloudTrail(ConsoleLogin) → CloudWatch Logs 구독 필터 → Lambda → Teams(사용자명 포함)
#   CloudWatch 알람은 메트릭 임계값만 담아 "누가 로그인했는지"를 못 실어 나른다 — 로그 구독 필터로
#   CloudTrail 원본 레코드(userIdentity.userName 등)를 그대로 Lambda에 넘겨야 사용자명이 나온다.
#   기존 [CLOUDTRAIL] 구역의 로그그룹(aws_cloudwatch_log_group.cloudtrail)을 그대로 구독한다.
# =============================================================================
resource "aws_cloudwatch_log_group" "login_notifier" {
  name              = "/aws/lambda/${var.project}-monitoring-login-notifier"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "login_notifier" {
  name               = "${var.project}-monitoring-login-notifier"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "login_notifier_logs" {
  role       = aws_iam_role.login_notifier.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "login_notifier" {
  statement {
    sid       = "ReadWebhookSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.teams_webhook_login.arn]
  }
}

resource "aws_iam_role_policy" "login_notifier" {
  name   = "read-webhook-secret"
  role   = aws_iam_role.login_notifier.id
  policy = data.aws_iam_policy_document.login_notifier.json
}

data "archive_file" "login_notifier" {
  type        = "zip"
  source_file = "${path.module}/lambda_src/login_notifier.py"
  output_path = "${path.module}/build/login_notifier.zip"
}

resource "aws_lambda_function" "login_notifier" {
  function_name    = "${var.project}-monitoring-login-notifier"
  role             = aws_iam_role.login_notifier.arn
  runtime          = "python3.12"
  handler          = "login_notifier.handler"
  filename         = data.archive_file.login_notifier.output_path
  source_code_hash = data.archive_file.login_notifier.output_base64sha256
  timeout          = 15
  memory_size      = 128
  environment {
    variables = {
      WEBHOOK_SECRET_ARN = aws_secretsmanager_secret.teams_webhook_login.arn
    }
  }
  depends_on = [aws_cloudwatch_log_group.login_notifier]
}

resource "aws_lambda_permission" "cwl_invoke_login_notifier" {
  statement_id  = "AllowCloudWatchLogsInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.login_notifier.function_name
  principal     = "logs.${var.region}.amazonaws.com"
  source_arn    = "${aws_cloudwatch_log_group.cloudtrail.arn}:*"
}

resource "aws_cloudwatch_log_subscription_filter" "login_notifier" {
  name            = "${var.project}-monitoring-console-login"
  log_group_name  = aws_cloudwatch_log_group.cloudtrail.name
  filter_pattern  = "{ $.eventName = \"ConsoleLogin\" }"
  destination_arn = aws_lambda_function.login_notifier.arn
  depends_on      = [aws_lambda_permission.cwl_invoke_login_notifier]
}

# =============================================================================
# [알람] 알림 피로 방지 — 진짜 조치가 필요한 것만(README §11 후보 표)
# =============================================================================
resource "aws_cloudwatch_metric_alarm" "sqs_dlq" {
  alarm_name          = "${var.project}-monitoring-sqs-dlq-nonempty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 0
  period              = 300
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = local.sqs_ingest_dlq }
  statistic           = "Maximum"
  alarm_description   = "정규화 실패 finding 존재(DLQ 적재) = 데이터 유실 위험"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}

# 6종 Lambda 전부 개별 알람(for_each) — lambda_names에 새 함수 추가되면 알람도 자동 생성.
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each            = toset(local.lambda_names)
  alarm_name          = "${each.value}-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 0
  period              = 300
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = each.value }
  statistic           = "Sum"
  alarm_description   = "Lambda 에러 발생(${each.value}) — 파이프라인 끊김 가능성"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "sfn_failed" {
  alarm_name          = "${var.project}-monitoring-remediation-sfn-failed"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 0
  period              = 300
  namespace           = "AWS/States"
  metric_name         = "ExecutionsFailed"
  dimensions          = { StateMachineArn = local.remediation_sfn_arn }
  statistic           = "Sum"
  alarm_description   = "HITL 조치 실행 실패 — 승인 흐름이 실패했는데 아무도 모르는 상황 방지"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "bedrock_errors" {
  alarm_name          = "${var.project}-monitoring-bedrock-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 0
  alarm_description   = "AI 조사(Bedrock 호출) 에러 — 엔진 조사 자체가 멈췄다는 신호"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "total_errors"
    expression  = "client_err + server_err"
    label       = "Bedrock 총 에러(Client+Server)"
    return_data = true
  }
  metric_query {
    id = "client_err"
    metric {
      namespace   = "AWS/Bedrock"
      metric_name = "InvocationClientErrors"
      # ModelId 디멘션 필수 — Bedrock 지표는 디멘션 없이 조회하면 데이터가 안 잡힘(무디멘션 롤업 없음).
      # 지금은 모델 1개(Haiku)뿐이라 [0] 고정 — Sonnet 추가 시 lambda_errors처럼 for_each로 전환 고려.
      dimensions = { ModelId = local.bedrock_model_ids[0] }
      period     = 300
      stat       = "Sum"
    }
  }
  metric_query {
    id = "server_err"
    metric {
      namespace   = "AWS/Bedrock"
      metric_name = "InvocationServerErrors"
      dimensions  = { ModelId = local.bedrock_model_ids[0] }
      period      = 300
      stat        = "Sum"
    }
  }
}

# 비용 가드레일 — 정밀 청구액 알람이 아니라 "무한루프·비정상 다량 호출"을 조기에 잡는 안전망.
# 위 "Bedrock 추정 비용" 위젯(y=bedrock_rows_end_y)과 동일한 metric math(토큰×단가)를 재사용,
# period만 300(위젯, 추세 확인용)→3600(알람, 시간당 예산 개념)으로 바꿔 스파이크성 오탐을 줄인다.
resource "aws_cloudwatch_metric_alarm" "bedrock_cost_high" {
  alarm_name          = "${var.project}-monitoring-bedrock-cost-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = var.bedrock_hourly_cost_alarm_usd
  alarm_description   = "Bedrock 추정 비용이 시간당 임계값 초과 — 무한루프·비정상 다량 tool-use 조기 감지(가드레일, 정밀 청구액 아님)"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "cost"
    expression  = "(m1/1000)*${var.bedrock_haiku_price_in_per_1k} + (m2/1000)*${var.bedrock_haiku_price_out_per_1k}"
    label       = "Haiku 추정비용(USD, 1시간)"
    return_data = true
  }
  metric_query {
    id = "m1"
    metric {
      namespace   = "AWS/Bedrock"
      metric_name = "InputTokenCount"
      dimensions  = { ModelId = local.bedrock_model_ids[0] }
      period      = 3600
      stat        = "Sum"
    }
  }
  metric_query {
    id = "m2"
    metric {
      namespace   = "AWS/Bedrock"
      metric_name = "OutputTokenCount"
      dimensions  = { ModelId = local.bedrock_model_ids[0] }
      period      = 3600
      stat        = "Sum"
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_connections" {
  alarm_name          = "${var.project}-monitoring-rds-connections-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = var.rds_connections_alarm_threshold
  period              = 300
  namespace           = "AWS/RDS"
  metric_name         = "DatabaseConnections"
  dimensions          = { DBInstanceIdentifier = local.rds_identifier }
  statistic           = "Average"
  alarm_description   = "RDS 연결 포화 — 조용히 장애로 번지기 전에"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}

# ⚠️ 아래 알람은 engine/reasoning/orchestrator.py EMF 계측(README §2③.1) 전까지 데이터가 없어
#    INSUFFICIENT_DATA에 머문다 — treat_missing_data=notBreaching이라 알림 스팸은 안 남(의도한 동작).
#    계측 완료 후 자동으로 살아나는 "뼈대" 알람(instruction: 지금 못 하는 건 확장 쉬운 뼈대로).
#    ⚠️ CloudWatch 알람은 metric math에서 SEARCH()를 지원하지 않는다(동적 시계열 개수라 단일
#    임계값 알람과 안 맞음) — 그래서 _emit_case_metrics가 무디멘션(Dimensions=[[]])으로도 같이
#    발행하는 FindingsEvaluated/FindingsEscalated를 SEARCH 없이 직접 참조한다(2026-07-03 수정,
#    원래 SEARCH를 썼다가 알람 생성 자체가 API에서 거부될 수 있는 버그였음).
resource "aws_cloudwatch_metric_alarm" "triage_escalate_rate_zero" {
  alarm_name          = "${var.project}-monitoring-triage-escalate-zero"
  comparison_operator = "LessThanOrEqualToThreshold"
  evaluation_periods  = 3
  threshold           = 0
  alarm_description   = "트리아지 게이트가 findings는 들어오는데 승급을 계속 0건으로 거르는 회귀 감지. ⚠️ orchestrator.py EMF 계측 전까진 INSUFFICIENT_DATA(정상)."
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "evaluated"
    return_data = false
    metric {
      namespace   = "CnappAgentic/Engine"
      metric_name = "FindingsEvaluated"
      period      = 900
      stat        = "Sum"
    }
  }
  metric_query {
    id          = "escalated"
    return_data = false
    metric {
      namespace   = "CnappAgentic/Engine"
      metric_name = "FindingsEscalated"
      period      = 900
      stat        = "Sum"
    }
  }
  metric_query {
    id          = "gate"
    expression  = "IF(evaluated > 0, escalated, 999)" # findings 자체가 없으면 999(무해) — evaluated>0인데 escalated=0일 때만 <=0 breach
    label       = "게이트 상태(0 이하 = findings는 있는데 승급 0건 = 회귀 의심)"
    return_data = true
  }
}
