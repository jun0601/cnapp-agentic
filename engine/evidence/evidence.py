"""Evidence 에이전트 (준형 담당) — 프로젝트의 심장(챗봇 탈출 기준).

escalate된 finding에 대해 **스스로 read-only 툴을 골라 호출**(tool use)해 증거를 모으고
가설을 확증/반증한다. 여기선 '어떤 툴을 호출할지'를 규칙(control→tool) 기반 플래너로 결정 —
실배포에선 이 플래너를 Bedrock LLM으로 교체(LLM이 tool 선택). 실행기(ToolExecutor)는 그대로.

계약④ allowlist 밖 툴은 실행기가 차단(read-only first). 변경 API는 절대 호출 안 함.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from engine.core.tools import ToolExecutor, ToolResult

# control_id → 조사에 쓸 read-only 툴(계약④ allowlist 내). 실배포선 LLM이 이 선택을 대체.
PLAN_BY_CONTROL: Dict[str, List[str]] = {
    "INTERNAL-S3-PUBLIC-001": ["s3:GetBucketPolicy", "s3:GetPublicAccessBlock"],
    "INTERNAL-DATA-PII-EXPOSED-001": ["macie2:GetFindings"],
    "INTERNAL-IAM-OVERPRIV-001": ["iam:SimulatePrincipalPolicy"],
    "INTERNAL-SG-OPEN-INGRESS-001": ["ec2:DescribeSecurityGroups"],
    "INTERNAL-SECRET-PLAINTEXT-001": [],  # 매니페스트 스캔 결과로 충분(툴 조사 불필요 예시)
}


@dataclass
class EvidenceOutput:
    evidence: List[dict]       # 계약⑦ case.evidence[]
    tool_calls_count: int
    confidence_score: float
    verdict: str               # confirmed | inconclusive | refuted
    plan: List[Tuple[str, str]]  # (tool, resource_id) 조사 계획(설명용)


def plan_investigation(findings: List[dict]) -> List[Tuple[str, str]]:
    """case의 finding들에서 (툴, resource_id) 조사 계획 생성(순서 = finding 순서)."""
    plan: List[Tuple[str, str]] = []
    for f in findings:
        rid = f.get("resource_id")
        if not rid:
            continue  # resource_id 없으면 조사 대상 아님(정규화 규칙상 원래 필수)
        for tool in PLAN_BY_CONTROL.get(f.get("control_id", ""), []):
            plan.append((tool, rid))
    return plan


def _verdict(confirming: int, total: int) -> Tuple[str, float]:
    if total == 0:
        return "inconclusive", 0.0
    conf = confirming / total
    if conf >= 0.6:
        return "confirmed", conf
    if conf >= 0.3:
        return "inconclusive", conf
    return "refuted", conf


class EvidenceAgent:
    """read-only 툴로 능동조사. executor만 갈아끼우면 목업↔실AWS 전환."""

    def __init__(self, executor: ToolExecutor) -> None:
        self.executor = executor

    def investigate(self, findings: List[dict]) -> EvidenceOutput:
        plan = plan_investigation(findings)
        results: List[ToolResult] = []
        for tool, resource_id in plan:
            # ★ Evidence가 '스스로' read-only API 호출(allowlist는 executor가 강제)
            results.append(self.executor.execute(tool, resource_id))

        confirming = sum(1 for r in results if r.confirms)
        verdict, confidence = _verdict(confirming, len(results))

        return EvidenceOutput(
            evidence=[r.to_evidence_item() for r in results],
            tool_calls_count=len(results),
            confidence_score=confidence,
            verdict=verdict,
            plan=plan,
        )
