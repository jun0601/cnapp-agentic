"""Orchestrator (진우 담당) — Triage→Hypothesis→Evidence→Reasoning 전체 루프.

목업: MockToolExecutor 기본. 실배포: RealToolExecutor(boto3/MS Graph) 주입.
run_demo.py가 이 클래스를 단일 진입점으로 호출한다.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from engine.core import case as case_mod
from engine.core.contracts import findings_by_id
from engine.core.tools import MockToolExecutor, ToolExecutor
from engine.evidence.evidence import EvidenceAgent
from engine.evidence.triage import triage
from engine.reasoning.hypothesis import HypothesisAgent
from engine.reasoning.reasoning import ReasoningAgent

# 골든 경로 조사 순서 — control_id 우선순위(데이터 노출 확인 → 도달 경로 확인)
_INVESTIGATION_ORDER = [
    "INTERNAL-S3-PUBLIC-001",
    "INTERNAL-DATA-PII-EXPOSED-001",
    "INTERNAL-IAM-OVERPRIV-001",
]


class Orchestrator:
    """에이전틱 조사 루프 오케스트레이터.

    실배포 스왑: Orchestrator(executor=RealToolExecutor()) 로 생성.
    Triage·Hypothesis·Evidence·Reasoning 로직은 무변 — executor만 갈아끼운다.
    """

    def __init__(self, executor: Optional[ToolExecutor] = None) -> None:
        self.executor = executor or MockToolExecutor()
        self._hyp = HypothesisAgent()
        self._ev = EvidenceAgent(self.executor)
        self._rsn = ReasoningAgent()

    def run(
        self,
        findings: List[dict],
        paths: List[dict],
        case_id: str = "c0000000-0000-4000-8000-000000000001",
    ) -> Tuple[dict, List[dict], List[dict]]:
        """전체 루프 실행.

        반환: (case, escalated_findings, case_findings)
          - case: 계약⑦ case 객체 (stage=reasoning 완료)
          - escalated_findings: 트리아지 통과 finding 전체
          - case_findings: 실제 Evidence가 조사한 finding 목록
        """
        fmap = findings_by_id(findings)
        golden_path_id = paths[0]["attack_path_id"] if paths else None

        # ── ① Triage ──────────────────────────────────────────────
        escalated = [f for f in findings if triage(f).escalate]

        # ── case_findings 선정: 골든 경로 소속 + 조사 가능 control ──
        if golden_path_id:
            candidate = [
                f for f in escalated
                if f.get("attack_path_id") == golden_path_id
                and f.get("control_id") in _INVESTIGATION_ORDER
            ]
            candidate.sort(
                key=lambda f: _INVESTIGATION_ORDER.index(f["control_id"])
            )
        else:
            candidate = escalated[:3]  # fallback: 상위 3건

        if not candidate:
            raise ValueError("조사 대상 finding 없음 — 종료")

        case_findings = candidate  # type: List[dict]
        finding_ids = [f["finding_id"] for f in case_findings]
        c = case_mod.new_case(case_id, finding_ids)

        top_score = max(triage(f).priority_score for f in case_findings)
        min_sev = min(int(f.get("severity_id", 5)) for f in case_findings)
        case_mod.set_triage(
            c, top_score, True,
            "escalate — attack_path_id!=null(골든 경로) · 최고 severity_id=%d" % min_sev,
        )

        # ── ② Hypothesis ──────────────────────────────────────────
        hypotheses = self._hyp.generate(escalated, paths)
        case_mod.set_hypotheses(c, hypotheses)

        # ── ③ Evidence ────────────────────────────────────────────
        ev_out = self._ev.investigate(case_findings)
        case_mod.set_evidence(
            c,
            ev_out.evidence,
            ev_out.tool_calls_count,
            ev_out.confidence_score,
            ev_out.verdict,
        )

        # ── ④ Reasoning ───────────────────────────────────────────
        rsn = self._rsn.analyze(c, fmap)
        case_mod.set_reasoning(c, rsn["narrative"], rsn["risk_level"], rsn["recommended_actions"])

        return c, escalated, case_findings
