"""GitHub Actions 전용 게시 스크립트(.github/workflows/access-analyzer-scan.yml가 실행).

AccessAnalyzerScanner.scan_access_analyzer()로 얻은 봉투를 EventBridge(기본 버스,
source=cnapp.scanner, detail-type=scan.completed)로 발행 → infra/backend의
aws_cloudwatch_event_rule.scanner_completed가 ingest Lambda로 라우팅.

Ingestor.publish()는 SQS 직접 발행(다른 스캐너용)이라 여기선 안 씀 — 이 경로는
Ingestor.from_eventbridge()의 커스텀 "scan.completed" 분기를 태운다(원래 있었지만
라이브 EventBridge 규칙이 없어 미사용이던 코드, 2026-07-08 처음 실사용).

로컬/CI 실행 시 boto3 자격증명 필요(GitHub OIDC role, infra/shared github_ci).
"""
from __future__ import annotations

import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from scanners.ciem.aws_access_analyzer import AccessAnalyzerScanError, AccessAnalyzerScanner

_EVENT_BUS = "default"
_BATCH_SIZE = 10  # EventBridge PutEvents 1회 최대 엔트리 수


def main() -> int:
    import boto3

    try:
        envelopes = AccessAnalyzerScanner().scan_access_analyzer()
    except AccessAnalyzerScanError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1

    if not envelopes:
        print("Access Analyzer ACTIVE finding 없음 — 발행할 것 없음")
        return 0

    entries = [
        {
            "Source": "cnapp.scanner",
            "DetailType": "scan.completed",
            "Detail": json.dumps(
                {
                    "source": env["source"],
                    "source_format": env["source_format"],
                    "cloud_hint": env["cloud_hint"],
                    "raw": env["raw_inline"],
                },
                default=str,  # boto3 datetime → ISO 문자열
                ensure_ascii=False,
            ),
            "EventBusName": _EVENT_BUS,
        }
        for env in envelopes
    ]

    events = boto3.client("events", region_name="ap-northeast-2")
    sent = 0
    failed = 0
    for i in range(0, len(entries), _BATCH_SIZE):
        batch = entries[i : i + _BATCH_SIZE]
        resp = events.put_events(Entries=batch)
        batch_failed = resp.get("FailedEntryCount", 0)
        failed += batch_failed
        sent += len(batch) - batch_failed
        if batch_failed:
            for item in resp.get("Entries", []):
                if item.get("ErrorCode"):
                    print(f"  실패: {item.get('ErrorCode')} {item.get('ErrorMessage')}", file=sys.stderr)

    print(f"{sent}/{len(entries)}건 발행 완료" + (f" ({failed}건 실패)" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
