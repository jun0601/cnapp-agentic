"""계약⑦ case 객체 빌더 — 에이전트 간 단일 핸드오프 객체.

각 에이전트가 자기 구간만 채워 다음으로 넘긴다(triage→hypothesis→evidence→reasoning).
준형 담당 = triage·evidence 구간까지. hypothesis·reasoning은 진우 에이전트가 채움.
"""
from __future__ import annotations

from typing import Dict, List, Optional


def new_case(case_id: str, finding_ids: List[str]) -> dict:
    """상관된 finding 묶음으로 빈 case 시작(stage=triage)."""
    return {
        "case_id": case_id,
        "finding": {"finding_ids": list(finding_ids)},
        "stage": "triage",
        "model_trace": [],
    }


def set_triage(case: dict, priority_score: float, escalate: bool, reason: str) -> dict:
    case["triage"] = {"priority_score": priority_score, "escalate": escalate, "reason": reason}
    case["stage"] = "triage"
    _trace(case, "triage", "haiku")
    return case


def set_hypotheses(case: dict, hypotheses: List[str]) -> dict:
    """(참고) hypothesis 단계는 진우 담당 — Evidence 계획 근거로만 사용."""
    case["hypotheses"] = list(hypotheses)
    case["stage"] = "hypothesis"
    return case


def set_reasoning(case: dict, narrative: str, risk_level: str, recommended_actions: List[str]) -> dict:
    case["reasoning"] = {
        "narrative": narrative,
        "risk_level": risk_level,
        "recommended_actions": list(recommended_actions),
    }
    case["stage"] = "reasoning"
    _trace(case, "reasoning", "sonnet")  # Reasoning은 Sonnet (실배포 시)
    return case


def set_evidence(
    case: dict, evidence: List[dict], tool_calls: int, confidence: float, verdict: str,
    tokens: int = 0,
) -> dict:
    case["evidence"] = evidence
    case["evidence_meta"] = {
        "tool_calls_count": tool_calls,
        "confidence_score": round(confidence, 3),
        "verdict": verdict,
    }
    case["stage"] = "evidence"
    # model_trace[].tokens는 계약⑦에 처음부터 있던 필드(비용 추적용)인데 지금까지 항상 0으로
    # 방치돼 있었음 — BedrockEvidenceAgent가 실 usage를 채워주면 여기로 흘러들어온다.
    _trace(case, "evidence", "haiku", tokens=tokens)
    return case


def _trace(case: dict, stage: str, model: str, tokens: int = 0) -> None:
    case.setdefault("model_trace", []).append({"stage": stage, "model": model, "tokens": tokens})


# case.schema.json 최소 정합 체크(엔진 자체 검증용 — 스키마 필수키)
_REQUIRED = {"case_id", "finding", "stage"}


def validate_shape(case: dict) -> List[str]:
    errs: List[str] = []
    for k in _REQUIRED:
        if k not in case:
            errs.append("필수키 누락: %s" % k)
    if "finding" in case and "finding_ids" not in case["finding"] and "finding_id" not in case["finding"]:
        errs.append("finding은 finding_ids[] 또는 단일 finding이어야 함")
    if case.get("stage") not in {"triage", "hypothesis", "evidence", "reasoning"}:
        errs.append("stage 값 부적합: %s" % case.get("stage"))
    # evidence 항목 형태 + evidence_meta.verdict enum(계약⑦)
    for i, e in enumerate(case.get("evidence") or []):
        for k in ("tool", "resource_id", "result_summary", "ts"):
            if k not in e:
                errs.append("evidence[%d] 필수키 누락: %s" % (i, k))
    meta = case.get("evidence_meta")
    if meta is not None and meta.get("verdict") not in {"confirmed", "refuted", "inconclusive"}:
        errs.append("evidence_meta.verdict 부적합: %s" % meta.get("verdict"))
    return errs
