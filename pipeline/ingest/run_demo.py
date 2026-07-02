"""수집부 데모 — EventBridge/S3 이벤트 → 계약⑤ 봉투 → (dry-run) SQS + 정규화 연결.

실행: 레포 루트에서  python -m pipeline.ingest.run_demo

흐름:
  1. Security Hub 'Findings Imported' EventBridge 이벤트 → from_eventbridge() → 봉투(inline)
  2. Prowler S3 드롭 이벤트 → from_s3_event() → 봉투(raw_location 포인터)
  3. publish() dry-run으로 SQS 발행 시뮬
  4. 이음새 증명: inline 봉투를 Normalizer(진우)에 넘겨 계약① finding으로 변환되는지
     (= 수집부 → 정규화부 계약⑤ 핸드오프가 실제로 물리는지)

실배포 스왑: publish(dry_run=False)+queue_url / lambda_handler를 EventBridge·S3 트리거에 연결.
"""
from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from pipeline.ingest.ingest import Ingestor
from pipeline.normalize.normalizer import Normalizer

# ── 입구 ① Security Hub Findings Imported (EventBridge) ───────────────
_SECURITYHUB_EVENT = {
    "id": "evt-0001",
    "detail-type": "Security Hub Findings - Imported",
    "source": "aws.securityhub",
    "detail": {
        "findings": [
            {
                "SchemaVersion": "2018-10-08",
                "Title": "S3 general purpose buckets should block public access",
                "Severity": {"Label": "HIGH"},
                "Resources": [{"Type": "AwsS3Bucket", "Id": "arn:aws:s3:::member-pii-prod"}],
                "Compliance": {"Status": "FAILED"},
                "ProductFields": {"ControlId": "S3.8"},
                "UpdatedAt": "2026-07-02T01:00:00Z", "CreatedAt": "2026-07-01T00:00:00Z",
            }
        ]
    },
}

# ── 입구 ② Prowler S3 드롭 (S3 ObjectCreated) ────────────────────────
_S3_EVENT = {
    "Records": [
        {"s3": {"bucket": {"name": "cnapp-raw-findings"},
                "object": {"key": "prowler-output/azure/2026-07-02/ocsf.json"}}}
    ]
}


def _hr(t: str) -> None:
    print("\n" + "=" * 64 + "\n" + t + "\n" + "=" * 64)


def _check_envelope(e: dict) -> bool:
    """계약⑤ required 6필드 + raw_inline/raw_location 중 하나 존재."""
    req = {"envelope_id", "source", "source_format", "cloud_hint", "scan_batch_id", "ingested_at"}
    has_req = req.issubset(e.keys())
    has_raw = ("raw_inline" in e) or ("raw_location" in e)
    return has_req and has_raw


def main() -> int:
    ing = Ingestor()

    _hr("수집부 데모 — 이벤트 → 계약⑤ 봉투 → SQS(dry-run) → 정규화 핸드오프")

    # ── 입구 ① EventBridge(Security Hub) ─────────────────────────────
    eb_envs = ing.from_eventbridge(_SECURITYHUB_EVENT)
    print("\n[입구① EventBridge / Security Hub Findings Imported]")
    for e in eb_envs:
        print("  봉투: source=%s format=%s cloud=%s raw=inline(%s)"
              % (e["source"], e["source_format"], e["cloud_hint"], "raw_inline" in e))

    # ── 입구 ② S3(Prowler 드롭) ──────────────────────────────────────
    s3_envs = ing.from_s3_event(_S3_EVENT)
    print("\n[입구② S3 ObjectCreated / Prowler 드롭]")
    for e in s3_envs:
        print("  봉투: source=%s format=%s cloud=%s raw=pointer(%s)"
              % (e["source"], e["source_format"], e["cloud_hint"], e.get("raw_location")))

    # ── SQS 발행(dry-run) ────────────────────────────────────────────
    ids = ing.publish(eb_envs + s3_envs, dry_run=True)
    _hr("SQS 발행 (dry-run)")
    print("발행 시뮬 %d건: %s" % (len(ids), ids))

    # ── 이음새 증명: 수집부 봉투 → 정규화부 → finding ─────────────────
    _hr("이음새 증명(계약⑤): 수집부 봉투 → Normalizer(진우) → 계약① finding")
    findings = Normalizer().normalize(eb_envs[0])
    for f in findings:
        print("  ✓ %s / %s / pillar=%s" % (f["control_id"], f["resource_id"], f["pillar"]))

    # ── 검증 ─────────────────────────────────────────────────────────
    _hr("검증")
    env_ok = all(_check_envelope(e) for e in eb_envs + s3_envs)
    seam_ok = any(f["control_id"] == "INTERNAL-S3-PUBLIC-001" for f in findings)
    ptr_ok = s3_envs and s3_envs[0].get("raw_location", "").startswith("s3://") \
        and s3_envs[0]["source"] == "prowler-azure"
    print("계약⑤ 봉투 형식(required+raw)     : %s" % ("OK ✅" if env_ok else "FAIL ⚠️"))
    print("수집→정규화 핸드오프(S3-PUBLIC)   : %s" % ("OK ✅" if seam_ok else "FAIL ⚠️"))
    print("S3 드롭=prowler-azure 포인터 추론 : %s" % ("OK ✅" if ptr_ok else "FAIL ⚠️"))
    ok = env_ok and seam_ok and bool(ptr_ok)
    print("\n전체: %s" % ("OK ✅" if ok else "FAIL ⚠️"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
