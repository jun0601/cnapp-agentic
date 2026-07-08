"""Lambda 진입점 — correlation (배치완료 이벤트 → RDS finding 상관 → attack_paths 적재 → 상관완료 이벤트).

infra/engine의 correlation Lambda가 배포(실코드 스왑 포인트). 로직=CorrelationEngine(correlation.py).
2-pass 배관: normalize가 발행한 cnapp.findings.batch.completed로 기동 → RDS에서 open finding 로드 →
R1~R5 상관 → attack_paths upsert + findings.attack_path_id backfill(RDS) →
cnapp.attackpath.correlation.completed 발행 → orchestrator Lambda 구독.

Lambda 설정:
  handler = "attackpath.correlation.handler.handler"
  env     = DB_HOST · DB_SECRET_ARN · EVENT_BUS_NAME(=default)
  psycopg2 레이어 + VPC. ⚠️ 실 RDS 코드 — apply 세션에서 검증. 스키마=infra/shared/db/schema.sql.
  레이어  xray-sdk(2026-07-07 추가, X-Ray 분산 트레이싱).
"""
from __future__ import annotations

import json
import os

from attackpath.correlation.correlation import CorrelationEngine

# X-Ray(2026-07-07): EventBridge는 트레이스를 자동 전파 안 하므로, normalize가 이벤트 detail에
# 실어 보낸 batch_id를 이 Lambda 자신의 세그먼트에 annotation으로 남기고 다음 이벤트로도 계속
# 전달한다(pipeline/normalize/handler.py 상단 주석 참고 — 진짜 트레이스 병합이 아니라 검색용 상관관계 키).
try:
    from aws_xray_sdk.core import patch_all, xray_recorder

    patch_all()
    _XRAY = True
except ImportError:
    _XRAY = False


def _xray_annotate(key: str, value: str) -> None:
    """안전한 annotation — 2026-07-08 실측 버그(FacadeSegmentMutationException, pipeline/normalize/
    handler.py 주석 참고) 이후 서브세그먼트 방식 + 광범위 try/except로 통일."""
    if not _XRAY:
        return
    try:
        sub = xray_recorder.begin_subsegment("annotate")
        if sub is not None:
            sub.put_annotation(key, value)
        xray_recorder.end_subsegment()
    except Exception:  # noqa: BLE001
        pass

# correlate()가 참조하는 계약① 필드만 로드(상관 규칙 R1~R5 입력)
_SELECT_OPEN = """
SELECT finding_id, cloud, resource_id, resource_type, pillar, control_id,
       title, severity_id, status, sources, dedup_key, priority_score,
       attack_path_id, ai_status
FROM findings
WHERE status = 'open';
"""

_UPSERT_PATH = """
INSERT INTO attack_paths (attack_path_id, severity_id, nodes, edges, narrative_text)
VALUES (%(attack_path_id)s, %(severity_id)s, %(nodes)s, %(edges)s, %(narrative_text)s)
ON CONFLICT (attack_path_id) DO UPDATE SET
  severity_id    = EXCLUDED.severity_id,
  nodes          = EXCLUDED.nodes,
  edges          = EXCLUDED.edges,
  narrative_text = EXCLUDED.narrative_text;
"""


def handler(event: dict, context=None) -> dict:
    batch_id = (event or {}).get("detail", {}).get("batch_id")
    if batch_id:
        _xray_annotate("batch_id", batch_id)

    findings = _load_open_findings()
    paths = CorrelationEngine().correlate(findings)  # 멤버 finding에 attack_path_id backfill(in-memory)
    _upsert_paths(paths)
    _backfill_findings(findings)  # in-memory backfill → RDS 반영
    _emit_correlation_completed(len(paths), batch_id)
    return {"paths": len(paths)}


def _load_open_findings() -> list:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_SELECT_OPEN)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def _upsert_paths(paths: list) -> None:
    if not paths:
        return
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            for p in paths:
                cur.execute(_UPSERT_PATH, {
                    "attack_path_id": p["attack_path_id"],
                    "severity_id": p["severity_id"],
                    "nodes": json.dumps(p["nodes"]),
                    "edges": json.dumps(p["edges"]),
                    "narrative_text": p.get("narrative_text", ""),
                })
    finally:
        conn.close()


def _backfill_findings(findings: list) -> None:
    """correlate가 in-memory로 채운 attack_path_id를 RDS findings에 반영."""
    marked = [f for f in findings if f.get("attack_path_id")]
    if not marked:
        return
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            for f in marked:
                cur.execute(
                    "UPDATE findings SET attack_path_id = %s WHERE finding_id = %s;",
                    (f["attack_path_id"], f["finding_id"]),
                )
    finally:
        conn.close()


def _emit_correlation_completed(count: int, batch_id: str | None) -> None:
    """batch_id는 normalize가 시작한 트레이싱 상관관계 키를 orchestrator까지 이어 전달(X-Ray, 2026-07-07)."""
    import boto3
    events = boto3.client("events", region_name=os.environ.get("AWS_REGION", "ap-northeast-2"))
    detail = {"paths": count}
    if batch_id:
        detail["batch_id"] = batch_id
    events.put_events(Entries=[{
        "Source": "cnapp.attackpath",
        "DetailType": "cnapp.attackpath.correlation.completed",
        "Detail": json.dumps(detail),
        "EventBusName": os.environ.get("EVENT_BUS_NAME", "default"),
    }])


def _connect():
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
