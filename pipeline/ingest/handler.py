"""Lambda 진입점 — ingest (EventBridge/S3 → 계약⑤ 봉투 → SQS).

infra/pipeline의 ingest Lambda가 이 핸들러를 배포한다(실코드 스왑 포인트).
비즈니스 로직은 Ingestor(ingest.py)에 있고, 여기서는 환경변수만 주입해 호출한다.

Lambda 설정:
  handler = "pipeline.ingest.handler.handler"   (pipeline 패키지째 번들)
  env     = QUEUE_URL(=infra/pipeline SQS ingest 큐 URL)
  런타임 boto3만 필요(psycopg2 불요) — RDS 접근 없음.
"""
from __future__ import annotations

import os

from pipeline.ingest.ingest import Ingestor


def handler(event: dict, context=None) -> dict:
    return Ingestor(
        queue_url=os.environ.get("QUEUE_URL"),
        region=os.environ.get("AWS_REGION", "ap-northeast-2"),
    ).lambda_handler(event, context)
