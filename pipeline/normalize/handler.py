"""Lambda 진입점 — normalize (SQS 봉투 → 계약① finding → RDS 적재 → 배치완료 이벤트).

infra/pipeline의 normalize Lambda가 이 핸들러를 배포(실코드 스왑 포인트).
로직은 Normalizer(normalizer.py). 여기서 SQS 배치 처리 + RDS upsert + 2-pass 트리거 이벤트를 얹는다.

Lambda 설정:
  handler = "pipeline.normalize.handler.handler"
  env     = DB_HOST · DB_SECRET_ARN(shared Secrets) · EVENT_BUS_NAME(=default)
  런타임   psycopg2 레이어 필요(RDS 접근). VPC(private subnet) 배치.

⚠️ 실 RDS 대상 코드 — 로컬/CI(무 DB)에서는 실행 불가, apply 세션에서 검증. 스키마=infra/shared/db/schema.sql.
"""
from __future__ import annotations

import json
import os

from pipeline.normalize.normalizer import Normalizer

_UPSERT = """
INSERT INTO findings (finding_id, cloud, resource_id, resource_type, pillar, control_id,
                      title, severity_id, status, sources, dedup_key, priority_score,
                      attack_path_id, ai_status, first_seen, last_seen, raw_ref)
VALUES (%(finding_id)s, %(cloud)s, %(resource_id)s, %(resource_type)s, %(pillar)s, %(control_id)s,
        %(title)s, %(severity_id)s, %(status)s, %(sources)s, %(dedup_key)s, %(priority_score)s,
        %(attack_path_id)s, %(ai_status)s, %(first_seen)s, %(last_seen)s, %(raw_ref)s)
ON CONFLICT (dedup_key) DO UPDATE SET
  last_seen   = EXCLUDED.last_seen,
  status      = EXCLUDED.status,
  severity_id = EXCLUDED.severity_id,
  title       = EXCLUDED.title,
  sources     = (SELECT ARRAY(SELECT DISTINCT e
                              FROM unnest(findings.sources || EXCLUDED.sources) AS e));
"""


def handler(event: dict, context=None) -> dict:
    norm = Normalizer()
    findings: list = []
    for rec in event.get("Records", []):
        envelope = json.loads(rec.get("body", "{}"))
        _hydrate(envelope)  # raw_location(S3 포인터) → raw_inline (실 Prowler OCSF 경로)
        findings.extend(norm.normalize(envelope))

    _upsert_findings(findings)
    _emit_batch_completed(len(findings))
    return {"normalized": len(findings)}


def _hydrate(envelope: dict) -> None:
    """봉투에 raw_location(s3://…)만 있고 raw_inline이 없으면 S3 원본을 가져와 raw_inline에 채운다.
    실 Prowler는 큰 OCSF 원본을 S3에 떨구고 봉투엔 포인터만 담으므로(계약⑤ from_s3_event) 정규화 전 하이드레이트 필수.
    (이게 없으면 Normalizer가 raw_inline만 읽어 실 Prowler 경로에서 finding 0건이 됨.)"""
    if envelope.get("raw_inline") is not None:
        return
    loc = envelope.get("raw_location")
    if not loc or not loc.startswith("s3://"):
        return
    import boto3
    bucket, _, key = loc[len("s3://"):].partition("/")
    obj = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-northeast-2")).get_object(
        Bucket=bucket, Key=key)
    envelope["raw_inline"] = json.loads(obj["Body"].read())


def _upsert_findings(findings: list) -> None:
    if not findings:
        return
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            for f in findings:
                cur.execute(_UPSERT, {
                    "finding_id": f["finding_id"],
                    "cloud": f["cloud"],
                    "resource_id": f["resource_id"],
                    "resource_type": f["resource_type"],
                    "pillar": f["pillar"],
                    "control_id": f["control_id"],
                    "title": f["title"],
                    "severity_id": f["severity_id"],
                    "status": f.get("status", "open"),
                    "sources": f.get("sources", []),
                    "dedup_key": f["dedup_key"],
                    "priority_score": f.get("priority_score"),
                    "attack_path_id": f.get("attack_path_id"),
                    "ai_status": f.get("ai_status", "pending"),
                    "first_seen": f["first_seen"],
                    "last_seen": f["last_seen"],
                    "raw_ref": f.get("raw_ref"),
                })
    finally:
        conn.close()


def _emit_batch_completed(count: int) -> None:
    """정규화 배치 완료 → EventBridge(기본 버스) → infra/engine 상관 Lambda 구독(2-pass)."""
    import boto3
    events = boto3.client("events", region_name=os.environ.get("AWS_REGION", "ap-northeast-2"))
    events.put_events(Entries=[{
        "Source": "cnapp.findings",
        "DetailType": "cnapp.findings.batch.completed",
        "Detail": json.dumps({"normalized": count}),
        "EventBusName": os.environ.get("EVENT_BUS_NAME", "default"),
    }])


def _connect():
    """shared Secrets Manager에서 자격증명 로드 → psycopg2 연결(지연 import)."""
    import boto3
    import psycopg2
    sm = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "ap-northeast-2"))
    sec = json.loads(sm.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"])
    return psycopg2.connect(
        host=os.environ["DB_HOST"], port=5432,
        dbname=sec.get("dbname", "cnapp"), user=sec["username"], password=sec["password"],
        connect_timeout=5,
        sslmode="require",  # in-transit TLS 강제(#2). 기본 'prefer'는 TLS 선택적 → require로 필수화(CA 핀닝 verify-full은 후속).
    )
