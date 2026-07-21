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


def set_hypotheses(
    case: dict, hypotheses: List[str], tokens: int = 0, model: str = "template",
) -> dict:
    """(참고) hypothesis 단계는 진우 담당 — Evidence 계획 근거로만 사용.

    2026-07-10: model_trace에 hypothesis 스테이지 자체가 누락돼있던 버그 수정
    (_trace 호출이 원래 없었음) — BedrockHypothesisAgent 실배포 시 tokens·model이
    실제 사용량으로 채워진다(mock 템플릿은 기본값 tokens=0/model="template" 유지).
    """
    case["hypotheses"] = list(hypotheses)
    case["stage"] = "hypothesis"
    _trace(case, "hypothesis", model, tokens=tokens)
    return case


def set_reasoning(
    case: dict, narrative: str, risk_level: str, recommended_actions: List[str],
    tokens: int = 0, model: str = "template", rag_refs: Optional[List[str]] = None,
) -> dict:
    case["reasoning"] = {
        "narrative": narrative,
        "risk_level": risk_level,
        "recommended_actions": list(recommended_actions),
        # 계약⑦이 처음부터 정의해뒀지만 2026-07-21까지 한 번도 안 채워지던 필드
        # (orchestrator에 RAG 배선이 없어 finding_explanations.rag_refs가 항상 []였다).
        # 콘솔 EvidenceTab이 작은 칩으로 렌더하므로 chunk UUID가 아니라 control_id를 담는다.
        "rag_refs": list(rag_refs or []),
    }
    case["stage"] = "reasoning"
    # 2026-07-10: "sonnet" 하드코딩 제거(이 계정은 Sonnet Marketplace 미승인이라 실제론 Haiku가
    # 돌면서 라벨만 sonnet으로 찍히는 오탐이었음) — 호출자(orchestrator)가 실제 agent의
    # model_label·last_tokens를 전달한다.
    _trace(case, "reasoning", model, tokens=tokens)
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
