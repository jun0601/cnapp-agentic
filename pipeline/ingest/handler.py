"""Lambda 진입점 — ingest (EventBridge/S3 → 계약⑤ 봉투 → SQS).

infra/pipeline의 ingest Lambda가 이 핸들러를 배포한다(실코드 스왑 포인트).
비즈니스 로직은 Ingestor(ingest.py)에 있고, 여기서는 환경변수만 주입해 호출한다.

Lambda 설정:
  handler = "pipeline.ingest.handler.handler"   (pipeline 패키지째 번들)
  env     = QUEUE_URL(=infra/pipeline SQS ingest 큐 URL)
  런타임 boto3만 필요(psycopg2 불요) — RDS 접근 없음.
  레이어  xray-sdk(2026-07-07 추가, X-Ray 분산 트레이싱).
"""
from __future__ import annotations

import os

from pipeline.ingest.ingest import Ingestor

# X-Ray(2026-07-07): boto3를 패치해 Ingestor.publish()의 sqs.send_message()가
# AWSTraceHeader 메시지 속성을 자동으로 실어 보내게 함 → normalize Lambda(Active tracing)가
# 이 값을 읽어 같은 트레이스로 자동 이어붙임(SQS+Lambda 네이티브 연동, 별도 코드 불필요).
# 레이어는 Lambda 배포에만 있고 로컬/CI(run_demo 등)엔 없으므로 조용히 건너뛴다.
try:
    from aws_xray_sdk.core import patch_all

    patch_all()
except ImportError:
    pass


def handler(event: dict, context=None) -> dict:
    return Ingestor(
        queue_url=os.environ.get("QUEUE_URL"),
        region=os.environ.get("AWS_REGION", "ap-northeast-2"),
    ).lambda_handler(event, context)
