"""Lambda 진입점 — normalize (SQS 봉투 → 계약① finding → RDS 적재 → 배치완료 이벤트).

infra/pipeline의 normalize Lambda가 이 핸들러를 배포(실코드 스왑 포인트).
로직은 Normalizer(normalizer.py). 여기서 SQS 배치 처리 + RDS upsert + 2-pass 트리거 이벤트를 얹는다.

Lambda 설정:
  handler = "pipeline.normalize.handler.handler"
  env     = DB_HOST · DB_SECRET_ARN(shared Secrets) · EVENT_BUS_NAME(=default)
  런타임   psycopg2 레이어 필요(RDS 접근). VPC(private subnet) 배치.
  레이어  xray-sdk(2026-07-07 추가, X-Ray 분산 트레이싱).

⚠️ 실 RDS 대상 코드 — 로컬/CI(무 DB)에서는 실행 불가, apply 세션에서 검증. 스키마=infra/shared/db/schema.sql.
"""
from __future__ import annotations

import json
import os
import uuid

from pipeline.normalize.normalizer import Normalizer

# X-Ray(2026-07-08 실측 정정): 애초 설계는 "SQS는 자동 연결, EventBridge는 수동"이었으나 실측 결과가
# 정반대로 나옴 —
#   · SQS→Lambda(ingest→normalize): ingest.py가 AWSTraceHeader를 MessageSystemAttributes에
#     명시적으로 실어도(patch_all만으론 안 됨) **트레이스 ID는 병합되지 않고 links[]로만 연결**된다
#     (SQS 배치가 여러 트레이스의 메시지를 섞을 수 있어 X-Ray가 단일 병합 대신 참조 링크를 씀 —
#     pipeline/ingest/ingest.py의 _xray_trace_header_attr() 주석 참고). 실패 아님, AWS 설계.
#   · EventBridge→Lambda(normalize→correlation→orchestrator): patch_all()만으로 **완전히 하나의
#     트레이스 ID로 병합**됨(bedrock-runtime·STS·IAM·secretsmanager 등 하위 서비스까지 한 트리에
#     실측 확인) — "EventBridge는 자동 전파 안 함"이라던 기존 가정이 틀렸음.
# 그래도 batch_id annotation은 유지: SQS 구간의 링크만으론 콘솔에서 바로 검색이 안 되니, 이 Lambda가
# 새로 생성하는 batch_id를 ① 이 세그먼트의 annotation으로 남기고 ② 다음 이벤트 detail에 실어보내
# correlation·orchestrator가 같은 값으로 자기 세그먼트에 annotation을 달게 한다 — X-Ray 콘솔에서
# annotation.batch_id로 검색하면 ingest부터 orchestrator까지 전 구간을 하나의 검색 키로 찾을 수 있다.
try:
    from aws_xray_sdk.core import patch_all, xray_recorder

    patch_all()
    _XRAY = True
except ImportError:
    _XRAY = False


def _xray_annotate(key: str, value: str) -> None:
    """X-Ray annotation을 안전하게 남긴다 — 관측 코드가 절대 실제 파이프라인을 깨면 안 된다.

    ⚠️ 2026-07-08 실측 버그: Lambda가 자동 생성하는 top-level 세그먼트는 aws_xray_sdk가
    'FacadeSegment'로 감싸 직접 mutation을 막는다(FacadeSegmentMutationException) — Active
    tracing Lambda에서 `xray_recorder.current_segment().put_annotation(...)`을 그대로 호출하면
    이 예외가 핸들러까지 전파돼 실제 로직(2-pass 이벤트 발행)까지 통째로 크래시시켰다(라이브
    normalize 호출 2건 모두 재현, cnapp.findings.batch.completed 미발행 확인). 서브세그먼트를
    열어 거기에 annotation을 남기는 것으로 수정(X-Ray는 서브세그먼트 annotation도 검색 가능) +
    무슨 일이 있어도 절대 예외를 밖으로 흘리지 않도록 광범위 try/except로 감쌈.
    """
    if not _XRAY:
        return
    try:
        sub = xray_recorder.begin_subsegment("annotate")
        if sub is not None:
            sub.put_annotation(key, value)
        xray_recorder.end_subsegment()
    except Exception:  # noqa: BLE001 — 관측 실패가 절대 비즈니스 로직을 막으면 안 됨
        pass

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
                              FROM unnest(findings.sources || EXCLUDED.sources) AS e))
RETURNING (xmax = 0) AS is_new;
"""
# xmax=0은 이 행이 INSERT였음을 뜻한다(UPDATE면 0이 아님) — 즉 "처음 보는 finding"인지
# "이미 아는 finding의 재유입"인지를 upsert 한 번으로 구분하는 표준 트릭.


def handler(event: dict, context=None) -> dict:
    norm = Normalizer()
    findings: list = []
    for rec in event.get("Records", []):
        envelope = json.loads(rec.get("body", "{}"))
        _hydrate(envelope)  # raw_location(S3 포인터) → raw_inline (실 Prowler OCSF 경로)
        findings.extend(norm.normalize(envelope))

    new_findings = _upsert_findings(findings)

    # 2-pass 트리거는 "하류가 실제로 할 일이 있을 때만" 발행한다(2026-07-24).
    # 조건 = 이번에 **처음 들어온** finding 중 **open**인 것이 하나라도 있을 때.
    #
    #   · suppressed 제외 — 하류(correlation→orchestrator)는 open만 본다(correlation 핸들러가
    #     OPEN만 로드하고 트리아지 게이트도 status=="open"을 요구). 깨워도 결과가 안 바뀐다.
    #   · 재유입(UPDATE) 제외 — Security Hub는 컴플라이언스 재평가 때마다 같은 finding을 반복
    #     발행한다. 상태가 그대로인데 다시 조사하면 같은 결론을 내려고 LLM만 태운다.
    #   · remediated 제외 — 조치로 인한 attack-path 소멸은 engine/remediation.py가 correlation을
    #     직접 재호출하는 별도 경로로 이미 처리된다(2026-07-10). 여기서 또 걸 필요가 없다.
    #
    # 이 조건이 없어서 실제로 터졌다(실측): Security Hub를 켜자 배치마다 파이프라인이 통째로
    # 재기동됐고 attack-path 3경로 배수까지 곱해져 2시간에 orchestrator 1053회, Bedrock 호출이
    # 시간당 98→528로 5배 뛰었다.
    #
    # 트리아지 게이트가 "어떤 finding을 조사할지"를 막는다면, 이 조건은 "엔진을 언제 깨울지"를
    # 막는다 — 게이트만으로는 재기동 빈도를 통제할 수 없다는 걸 이 사고가 보여줬다.
    trigger = [f for f in new_findings if f.get("status") == "open"]
    if trigger:
        _emit_batch_completed(len(trigger))
    return {"normalized": len(findings), "new": len(new_findings),
            "new_open": len(trigger), "engine_triggered": bool(trigger)}


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


def _upsert_findings(findings: list) -> list:
    """upsert 후 **이번에 처음 들어온(INSERT된)** finding 목록을 돌려준다.

    재유입(UPDATE)과 신규(INSERT)를 구분하는 이유: Security Hub는 같은 finding을 컴플라이언스
    재평가 때마다 반복 발행한다. 상태가 그대로인 재유입까지 엔진을 깨우면 동일한 결론을 내려고
    LLM을 계속 호출하게 된다(실측: orchestrator가 25분에 11회 돌며 tool-use 루프까지 태움).
    """
    if not findings:
        return []
    new_findings: list = []
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
                row = cur.fetchone()
                if row and row[0]:  # is_new
                    new_findings.append(f)
    finally:
        conn.close()
    return new_findings


def _emit_batch_completed(count: int) -> None:
    """정규화 배치 완료 → EventBridge(기본 버스) → infra/engine 상관 Lambda 구독(2-pass).

    batch_id는 이 배치를 대표하는 트레이싱 전용 상관관계 키(X-Ray annotation, 2026-07-07) —
    findings 테이블·비즈니스 로직과는 무관, 순수 관측용으로만 이벤트 detail에 실어 보낸다.
    """
    batch_id = str(uuid.uuid4())
    _xray_annotate("batch_id", batch_id)

    import boto3
    events = boto3.client("events", region_name=os.environ.get("AWS_REGION", "ap-northeast-2"))
    events.put_events(Entries=[{
        "Source": "cnapp.findings",
        "DetailType": "cnapp.findings.batch.completed",
        "Detail": json.dumps({"normalized": count, "batch_id": batch_id}),
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
