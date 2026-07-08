"""수집부 (준형 담당) — 스캐너 이벤트 → 계약⑤ ingest-envelope → SQS.

정규화부(pipeline/normalize, 진우)의 **producer 쪽 대칭**. 계약⑤가 이음새:
수집부는 봉투를 SQS에 싣고, 정규화 Lambda가 꺼내 계약① finding으로 변환한다.

입구가 둘(계약⑤ 설명):
  ① AWS 스캐너 EventBridge 이벤트 — 예: Security Hub 'Findings Imported'(detail.findings=[ASFF]),
     또는 커스텀 'cnapp.scanner scan.completed'(detail에 source/format/raw).
  ② Prowler가 S3에 떨군 OCSF 객체의 S3 ObjectCreated 이벤트 — 큰 원본이라 raw_location(포인터).
수집부가 이 둘을 하나의 봉투 형태로 흡수 → 정규화부는 봉투 하나만 보면 됨(입구를 몰라도 됨).

mock-first: from_eventbridge()/from_s3_event()가 봉투를 만들고, publish()는 dry-run(반환만).
실 경로(지연 import): publish()가 boto3 sqs.send_message. lambda_handler()가 실배포 진입점.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

_SOURCES = {"securityhub", "config", "inspector", "prowler-aws", "prowler-azure",
            "trivy", "kube-bench", "macie", "access-analyzer", "synthetic"}
_FORMATS = {"asff", "ocsf", "prowler-json", "trivy-json", "custom"}


def _xray_trace_header_attr() -> Optional[dict]:
    """X-Ray(2026-07-08): SQS→Lambda 트레이스 연결은 patch_all()만으론 자동으로 안 됨 —
    범용 botocore 패치는 API 호출을 subsegment로만 감쌀 뿐, SQS 메시지에 AWSTraceHeader를
    실어주진 않는다(EventBridge PutEvents의 TraceHeader 파라미터와 달리 SQS는 명시적으로
    MessageSystemAttributes에 얹어야 함). 현재 세그먼트(Lambda가 자동 생성한 FacadeSegment도
    읽기는 가능)에서 trace_id·segment_id·sampled를 직접 읽어 AWS 규격 문자열로 조립 후 시스템
    속성에 부착한다. 실패해도(로컬/CI 등 X-Ray 없음) None을 반환해 호출부가 그냥 생략하게 한다.

    ⚠️ 실측 확인(2026-07-08): 이 헤더를 실어도 ingest·normalize는 여전히 **서로 다른 트레이스
    ID**로 남는다 — 이건 실패가 아니라 SQS 이벤트소스의 X-Ray 설계 자체다. Lambda가 SQS를
    폴링하는 배치 호출은 여러 트레이스에서 온 메시지를 한 배치에 담을 수 있어 단일 부모 트레이스로
    흡수(병합)하지 않고, 대신 자기 트레이스에 `links[]`(reference_type=child)로 원본 트레이스를
    참조만 남긴다(X-Ray batch-get-traces로 실제 확인: ingest 세그먼트의 links[0].trace_id가
    normalize가 속한 트레이스 ID와 정확히 일치). EventBridge 구간(normalize→correlation→
    orchestrator)이 진짜 단일 트레이스로 병합되는 것과 대조적 — SQS는 "링크", EventBridge는
    "병합". X-Ray 콘솔에서 ingest 트레이스를 열면 링크를 타고 normalize 트레이스로 이동 가능."""
    try:
        from aws_xray_sdk.core import xray_recorder
        seg = xray_recorder.current_segment()
        if seg is None:
            return None
        header = "Root=%s;Parent=%s;Sampled=%d" % (seg.trace_id, seg.id, 1 if seg.sampled else 0)
        return {"AWSTraceHeader": {"DataType": "String", "StringValue": header}}
    except Exception:  # noqa: BLE001 — 트레이싱 실패가 발행 자체를 막으면 안 됨
        return None


class IngestError(Exception):
    """봉투화 실패(이벤트 형식 불명·enum 위반)."""


class Ingestor:
    """이벤트 → 계약⑤ 봉투 → SQS 발행.

    mock: publish() dry-run(반환만). real: SQS send_message(지연 import boto3).
    """

    def __init__(self, queue_url: Optional[str] = None, region: str = "ap-northeast-2",
                 profile: Optional[str] = None) -> None:
        self._queue_url = queue_url
        self._region = region
        self._profile = profile

    def _envelope(self, source: str, source_format: str, cloud_hint: str,
                  scan_batch_id: str, raw_inline: Optional[dict] = None,
                  raw_location: Optional[str] = None) -> dict:
        if source not in _SOURCES:
            raise IngestError("source enum 위반(계약⑤): %s" % source)
        if source_format not in _FORMATS:
            raise IngestError("source_format enum 위반(계약⑤): %s" % source_format)
        env = {
            "envelope_id": str(uuid.uuid4()),
            "source": source,
            "source_format": source_format,
            "cloud_hint": cloud_hint,
            "scan_batch_id": scan_batch_id,
            "ingested_at": _now(),
        }
        # raw_inline / raw_location 택1(둘 다 계약⑤ optional). 큰 원본은 포인터.
        if raw_inline is not None:
            env["raw_inline"] = raw_inline
        if raw_location is not None:
            env["raw_location"] = raw_location
        return env

    # ── 입구 ① EventBridge ────────────────────────────────────────────
    def from_eventbridge(self, event: dict) -> List[dict]:
        """EventBridge 이벤트 → 계약⑤ 봉투[](finding 1건=봉투 1개).

        지원 형태:
          - Security Hub 'Findings Imported': detail.findings=[ASFF...]
          - 커스텀 'scan.completed': detail={source, source_format, cloud_hint, raw|raw_location}
        """
        detail_type = event.get("detail-type", "")
        detail = event.get("detail", {})
        batch = event.get("id", str(uuid.uuid4()))

        if "Security Hub Findings" in detail_type:
            findings = detail.get("findings", [])
            return [self._envelope("securityhub", "asff", "aws",
                                   "securityhub-%s" % batch, raw_inline=asff)
                    for asff in findings]

        # 커스텀 스캐너 이벤트(cnapp.scanner)
        src = detail.get("source")
        fmt = detail.get("source_format")
        cloud = detail.get("cloud_hint", "aws")
        if not src or not fmt:
            raise IngestError("알 수 없는 EventBridge 형태: %s" % detail_type)
        return [self._envelope(src, fmt, cloud, "%s-%s" % (src, batch),
                               raw_inline=detail.get("raw"),
                               raw_location=detail.get("raw_location"))]

    # ── 입구 ② S3 이벤트(Prowler 드롭) ────────────────────────────────
    def from_s3_event(self, event: dict) -> List[dict]:
        """S3 ObjectCreated 이벤트(Prowler가 떨군 결과) → 계약⑤ 봉투[](raw_location 포인터).

        키 경로로 provider 추론: .../azure/... → prowler-azure, 그 외 prowler-aws.
        큰 원본이므로 인라인 대신 s3 포인터(raw_location) — 정규화 Lambda가 가져가 파싱.
        """
        envelopes: List[dict] = []
        for rec in event.get("Records", []):
            s3 = rec.get("s3", {})
            bucket = s3.get("bucket", {}).get("name", "")
            key = s3.get("object", {}).get("key", "")
            is_azure = "azure" in key.lower()
            source = "prowler-azure" if is_azure else "prowler-aws"
            cloud = "azure" if is_azure else "aws"
            envelopes.append(self._envelope(
                source, "ocsf", cloud,
                "%s-%s" % (source, _now_batch()),
                raw_location="s3://%s/%s" % (bucket, key),
            ))
        return envelopes

    # ── SQS 발행 ──────────────────────────────────────────────────────
    def publish(self, envelopes: List[dict], dry_run: bool = True) -> List[str]:
        """봉투[]를 SQS(ingest 큐)로 발행. dry_run=True면 발행 없이 envelope_id만 반환(mock).

        실배포: dry_run=False + queue_url 설정 → boto3 sqs.send_message.
        """
        if dry_run or not self._queue_url:
            return [e["envelope_id"] for e in envelopes]
        import json
        import boto3
        session = boto3.Session(profile_name=self._profile, region_name=self._region)
        sqs = session.client("sqs")
        attrs = _xray_trace_header_attr()
        ids: List[str] = []
        for e in envelopes:
            kwargs = {"QueueUrl": self._queue_url, "MessageBody": json.dumps(e)}
            if attrs:
                kwargs["MessageSystemAttributes"] = attrs
            resp = sqs.send_message(**kwargs)
            ids.append(resp["MessageId"])
        return ids

    # ── 실배포 진입점(Lambda) ─────────────────────────────────────────
    def lambda_handler(self, event: dict, context=None) -> dict:
        """EventBridge/S3 이벤트를 받아 봉투화→SQS 발행. 실배포 Lambda 핸들러.

        이벤트 형태로 입구 자동 판별(Records 있으면 S3, 아니면 EventBridge).
        """
        if "Records" in event:
            envelopes = self.from_s3_event(event)
        else:
            envelopes = self.from_eventbridge(event)
        ids = self.publish(envelopes, dry_run=False)
        return {"published": len(ids), "message_ids": ids}


# ── 헬퍼 ──────────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_batch() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
