"""트리아지 게이트 (준형 담당) — 비용 통제의 핵심.

finding 1000건이라도 '풀 조사 루프(Hypothesis→Evidence)'로 승급하는 건 소수만.
게이트 = severity_id<=2 (High/Critical) OR attack_path_id!=null (경로 후보).
승급된 것만 Evidence가 read-only 툴로 능동조사 → Bedrock 비용 통제(project-draft 9·15번).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TriageResult:
    escalate: bool
    priority_score: float
    reason: str


def triage(finding: dict) -> TriageResult:
    """단일 finding 트리아지. escalate 여부 + 우선순위 점수."""
    sev = int(finding.get("severity_id", 5))
    on_path = finding.get("attack_path_id") is not None
    status = finding.get("status", "open")

    # 게이트(4.4 2-pass): High↑(sev<=2) 또는 attack-path 후보만 승급
    escalate = status == "open" and (sev <= 2 or on_path)

    # 우선순위 점수 — 심각도(낮을수록 심각) 역수 + 경로 가산. 이미 계산돼 있으면 존중.
    if finding.get("priority_score") is not None:
        score = float(finding["priority_score"])
    else:
        score = (6 - sev) / 5.0  # sev1→1.0 … sev5→0.2
        if on_path:
            score = min(1.0, score + 0.25)  # 경로 소속이면 가산(독성 조합)

    if escalate:
        # 게이트는 OR — 실제로 충족된 드라이버만 나열
        drivers = []
        if sev <= 2:
            drivers.append("severity_id=%d(High↑)" % sev)
        if on_path:
            drivers.append("attack_path_id!=null")
        reason = "escalate — " + " · ".join(drivers)
    else:
        parts = ["severity_id=%d" % sev]
        if not on_path:
            parts.append("attack_path_id=null")
        if status != "open":
            parts.append("status=%s(비-open)" % status)
        reason = "hold — " + " / ".join(parts)

    return TriageResult(escalate=escalate, priority_score=round(score, 3), reason=reason)
