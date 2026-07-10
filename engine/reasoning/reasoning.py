"""Reasoning 에이전트 (진우 담당) — Evidence 결과를 내러티브·리포트로 변환.

목업: verdict + evidence + control 기반 템플릿으로 한국어 내러티브 생성.
실배포 스왑: analyze() 내 내러티브 생성 부분을 Bedrock Sonnet LLM 호출로 교체 —
  LLM이 evidence 전체를 읽고 자연어 내러티브 작성(인터페이스 무변).
"""
from __future__ import annotations

from typing import Dict, List


def _risk_level(verdict: str, confidence: float) -> str:
    if verdict == "confirmed" and confidence >= 0.8:
        return "critical"
    if verdict == "confirmed":
        return "high"
    if verdict == "inconclusive":
        return "medium"
    return "low"


def _build_narrative(case: dict, findings_map: Dict[str, dict]) -> str:
    meta = case.get("evidence_meta", {})
    verdict = meta.get("verdict", "inconclusive")
    confidence = meta.get("confidence_score", 0.0)
    tool_calls = meta.get("tool_calls_count", 0)
    evidence = case.get("evidence", [])
    finding_ids = case.get("finding", {}).get("finding_ids", [])

    titles = []
    for fid in finding_ids:
        f = findings_map.get(fid, {})
        t = f.get("title") or f.get("control_id", fid)
        titles.append(t)
    title_str = " / ".join(titles) if titles else "관련 finding"

    # evidence 중 위험을 뒷받침하는 항목 요약
    key_items = [
        e["result_summary"] for e in evidence
        if any(kw in e.get("result_summary", "")
               for kw in ("허용", "공개", "PII", "측면이동", "block 미설정"))
    ]

    if verdict == "confirmed":
        detail = " ".join(key_items[:2]) + ". " if key_items else ""
        return (
            "에이전트가 read-only 툴 %d회 능동 조사한 결과, "
            "해당 케이스(%s)의 위험이 실환경에서 확증되었습니다(신뢰도 %.0f%%). "
            "%s즉각적인 조치가 필요합니다."
            % (tool_calls, title_str, confidence * 100, detail)
        )
    if verdict == "inconclusive":
        return (
            "에이전트가 read-only 툴 %d회 조사하였으나 "
            "해당 케이스(%s)의 위험을 확증하기에 증거가 불충분합니다(신뢰도 %.0f%%). "
            "추가 수동 검토가 권장됩니다."
            % (tool_calls, title_str, confidence * 100)
        )
    return (
        "에이전트가 read-only 툴 %d회 조사한 결과, "
        "해당 케이스(%s)는 오탐으로 판단됩니다(신뢰도 %.0f%%). "
        "suppressed 처리를 검토하세요."
        % (tool_calls, title_str, confidence * 100)
    )


def _recommended_actions(verdict: str, findings: List[dict]) -> List[str]:
    if verdict != "confirmed":
        return ["수동 검토 후 suppressed 또는 acknowledged 처리"]

    ctrl_ids = {f.get("control_id", "") for f in findings}
    actions = []  # type: List[str]

    if "INTERNAL-S3-PUBLIC-001" in ctrl_ids:
        actions.append("S3 퍼블릭 액세스 차단(Block Public Access) 즉시 활성화")
    if "INTERNAL-DATA-PII-EXPOSED-001" in ctrl_ids:
        actions.append("Macie 분류 결과 기반 PII 파일 접근 제한 + 감사로그 보존")
    if "INTERNAL-IAM-OVERPRIV-001" in ctrl_ids:
        actions.append("IRSA 역할 권한 최소화(s3:* → 특정 버킷 ARN 한정)")
    if "INTERNAL-SG-OPEN-INGRESS-001" in ctrl_ids:
        actions.append("보안그룹 인바운드 0.0.0.0/0 제거 → 필요 CIDR만 허용")
    if "INTERNAL-SECRET-PLAINTEXT-001" in ctrl_ids:
        actions.append("평문 자격증명을 Secrets Manager로 이전 + 해당 SP 자격증명 즉시 교체")
    if "INTERNAL-ENTRA-SP-CRED-001" in ctrl_ids or "INTERNAL-ENTRA-INSECURE-CFG-001" in ctrl_ids:
        actions.append("Azure SP 자격증명 만료일 설정(데모 종료일 +1주) + 권한 최소화")

    if not actions:
        actions.append("HITL 승인 → Step Functions 자동 조치 요청")

    return actions


class ReasoningAgent:
    """Evidence 결과 → 한국어 내러티브 + 위험 수준 + 권고사항.

    실배포 스왑: analyze() 내 내러티브 생성을 Bedrock Sonnet LLM 호출로 교체.
    반환 딕셔너리 구조(narrative·risk_level·recommended_actions)는 동일하게 유지.
    """

    # orchestrator가 호출 후 읽는 관측용 속성 — HypothesisAgent와 동일 패턴.
    last_tokens = (0, 0)
    model_label = "template"

    def analyze(self, case: dict, findings_map: Dict[str, dict]) -> dict:
        """case(evidence 완료)를 받아 reasoning 결과 딕셔너리를 반환한다."""
        meta = case.get("evidence_meta", {})
        verdict = meta.get("verdict", "inconclusive")
        confidence = meta.get("confidence_score", 0.0)

        finding_ids = case.get("finding", {}).get("finding_ids", [])
        findings = [findings_map[fid] for fid in finding_ids if fid in findings_map]

        return {
            "narrative": _build_narrative(case, findings_map),
            "risk_level": _risk_level(verdict, confidence),
            "recommended_actions": _recommended_actions(verdict, findings),
        }
