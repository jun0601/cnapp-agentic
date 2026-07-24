"""soc/ 독립 데모 — GuardDuty finding → SOC event 변환·출력.

  python -m soc.run_demo          # mock fixture (CI 안전, 계정 불필요)
  python -m soc.run_demo --live   # 라이브 GuardDuty read-only collect

이 데모는 계약 스키마·RDS·콘솔을 일절 건드리지 않는다 — 코어 CNAPP과 분리돼
"SOC 확장 훅이 실제로 작동한다"만 증명한다. 자세한 배경은 soc/README.md 참조.
"""
from __future__ import annotations

import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 UTF-8
except Exception:
    pass

from soc.collector import GuardDutyCollector, SocEvent

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "guardduty-c2-dns.json")


def _print_event(e: SocEvent) -> None:
    print(f"  · [{e.severity_label} {e.severity_score}] {e.threat_type}")
    print(f"    resource : {e.resource_type} {e.resource}")
    print(f"    indicator: {e.action_type} -> {e.indicator}  (observed {e.observed_count}x)")
    print(f"    detected : {e.detected_at}  (event, 불변 — CNAPP finding처럼 remediated로 사라지지 않음)")


def main(live: bool = False) -> int:
    collector = GuardDutyCollector()

    if live:
        print("== 라이브 GuardDuty read-only collect ==")
        events = collector.collect()
    else:
        print("== mock fixture (guardduty get-findings 원본 구조) ==")
        with open(_FIXTURE, encoding="utf-8") as fh:
            raw = json.load(fh)
        events = collector.collect_from_json(raw)

    print(f"수집된 SOC 이벤트: {len(events)}건\n")
    for e in events:
        _print_event(e)
        print()

    # ── 코어 분리 불변식 자기검증 (이 데모의 존재 이유) ──────────────
    assert all(e.source == "guardduty" for e in events)
    assert all(e.kind == "runtime-threat-event" for e in events)
    for e in events:
        d = e.to_dict()
        # SOC event는 CNAPP finding 필드(status·attack_path_id·control_id·dedup_key)를
        # 갖지 않는다 — 계약 모델과 분리돼 있음을 코드로 강제.
        for cnapp_field in ("status", "attack_path_id", "control_id", "dedup_key"):
            assert cnapp_field not in d, f"SOC event가 CNAPP finding 필드({cnapp_field})를 가지면 안 된다"
        # severity는 CNAPP의 1~5가 아니라 GuardDuty 0.0~8.9 스케일이어야 한다.
        assert 0.0 <= e.severity_score <= 8.9, "GuardDuty severity 스케일(0.0~8.9)"

    print("OK — SOC 확장 훅 데모 통과")
    print("     (SOC event 모델이 CNAPP 계약 finding과 분리돼 있음을 확인 — 코어 미접촉)")
    return 0


if __name__ == "__main__":
    sys.exit(main(live="--live" in sys.argv))
