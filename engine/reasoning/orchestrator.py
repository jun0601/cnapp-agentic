"""Orchestrator (진우 담당) — Triage→Hypothesis→Evidence→Reasoning 전체 루프.

목업: MockToolExecutor 기본. 실배포: RealToolExecutor(boto3/MS Graph) 주입.
run_demo.py가 이 클래스를 단일 진입점으로 호출한다.
"""
from __future__ import annotations

import json
import os
import time
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


def _emit_case_metrics(
    case: dict, findings_n: int, escalated_n: int, elapsed_ms: float,
    input_tokens: int = 0, output_tokens: int = 0,
) -> None:
    """EMF(Embedded Metric Format) 한 줄 — infra/monitoring 대시보드·알람(CnappAgentic/Engine
    네임스페이스)이 이 로그 라인을 파싱한다(계측은 이미 여기 존재 — Lambda 밖 로컬 실행에서만
    미발행이라 run_demo/run_e2e 콘솔엔 안 찍힌다). 별도 의존성·비용 없음.

    Dimensions에 빈 세트([])와 ["Verdict","RiskLevel"]를 함께 선언 — 한 줄로 ① 무디멘션 집계
    시계열(대시보드 총계 위젯·알람이 SEARCH 없이 직접 조회 가능 — CloudWatch 알람은 SEARCH를
    지원하지 않음) ② Verdict×RiskLevel 세부분해 시계열을 동시에 발행한다(EMF 표준 기능, 추가
    print 불필요).

    input_tokens/output_tokens: 케이스 1건(=Evidence investigate() 1회 호출) 전체의 Bedrock
    토큰 합 — 규칙 플래너(EvidenceAgent)는 LLM을 안 써서 항상 0. 이 값 자체로 "케이스별 비용"을
    보는 게 아니라(카디널리티 폭발 방지 — CaseId는 지표 Dimension이 아니라 로그 필드로만 둠),
    CloudWatch Logs Insights로 이 EMF 로그 라인을 CaseId로 직접 검색해서 조회한다
    (infra/monitoring/README.md §2③.3 참고).
    """
    if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return  # Lambda 밖(run_demo/run_e2e 로컬 실행)에선 콘솔 스팸 방지 위해 미발행
    meta = case.get("evidence_meta", {})
    reasoning = case.get("reasoning", {})
    emf = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": "CnappAgentic/Engine",
                "Dimensions": [[], ["Verdict", "RiskLevel"]],
                "Metrics": [
                    {"Name": "FindingsEvaluated", "Unit": "Count"},
                    {"Name": "FindingsEscalated", "Unit": "Count"},
                    {"Name": "ToolCallsPerCase", "Unit": "Count"},
                    {"Name": "ConfidenceScore", "Unit": "None"},
                    {"Name": "TimeToVerdictMs", "Unit": "Milliseconds"},
                    {"Name": "BedrockInputTokens", "Unit": "Count"},
                    {"Name": "BedrockOutputTokens", "Unit": "Count"},
                ],
            }],
        },
        "Verdict": meta.get("verdict", "unknown"),
        "RiskLevel": reasoning.get("risk_level", "unknown"),
        "CaseId": case.get("case_id"),
        "FindingsEvaluated": findings_n,
        "FindingsEscalated": escalated_n,
        "ToolCallsPerCase": meta.get("tool_calls_count", 0),
        "ConfidenceScore": meta.get("confidence_score", 0.0),
        "TimeToVerdictMs": elapsed_ms,
        "BedrockInputTokens": input_tokens,
        "BedrockOutputTokens": output_tokens,
    }
    print(json.dumps(emf))


def _emit_tool_usage_metrics(case_id: str, plan: List[Tuple[str, str]]) -> None:
    """어떤 read-only 툴이 몇 번 호출됐는지(tool별 breakdown) — 별도 EMF 라인.

    EMF는 한 로그 라인 = 한 Dimension 값 세트라, 케이스 하나에서 tool이 여러 종류
    호출됐으면 tool마다 라인을 하나씩 찍어야 한다(총계 위젯처럼 한 줄로 묶을 수 없음
    — Dimensions=[["Tool"]]로 CloudWatch가 Tool별 시계열을 자동으로 쪼개준다).
    """
    if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return
    counts: Dict[str, int] = {}
    for tool, _resource_id in plan:
        counts[tool] = counts.get(tool, 0) + 1
    ts = int(time.time() * 1000)
    for tool, count in counts.items():
        emf = {
            "_aws": {
                "Timestamp": ts,
                "CloudWatchMetrics": [{
                    "Namespace": "CnappAgentic/Engine",
                    "Dimensions": [["Tool"]],
                    "Metrics": [{"Name": "ToolInvocations", "Unit": "Count"}],
                }],
            },
            "Tool": tool,
            "CaseId": case_id,
            "ToolInvocations": count,
        }
        print(json.dumps(emf))


class Orchestrator:
    """에이전틱 조사 루프 오케스트레이터.

    실배포 스왑: Orchestrator(executor=RealToolExecutor()) 로 생성.
    Triage·Hypothesis·Evidence·Reasoning 로직은 무변 — executor만 갈아끼운다.
    """

    def __init__(
        self,
        executor: Optional[ToolExecutor] = None,
        evidence_agent: Optional[object] = None,
    ) -> None:
        # evidence_agent: 규칙 플래너(EvidenceAgent, 기본) ↔ LLM 플래너(BedrockEvidenceAgent)
        # 스왑 지점. 둘 다 investigate(findings)->EvidenceOutput 동일 인터페이스.
        self.executor = executor or MockToolExecutor()
        self._hyp = HypothesisAgent()
        self._ev = evidence_agent or EvidenceAgent(self.executor)
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
        t0 = time.time()
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
            tokens=ev_out.input_tokens + ev_out.output_tokens,
        )

        # ── ④ Reasoning ───────────────────────────────────────────
        rsn = self._rsn.analyze(c, fmap)
        case_mod.set_reasoning(c, rsn["narrative"], rsn["risk_level"], rsn["recommended_actions"])

        _emit_case_metrics(
            c, len(findings), len(escalated), (time.time() - t0) * 1000,
            input_tokens=ev_out.input_tokens, output_tokens=ev_out.output_tokens,
        )
        _emit_tool_usage_metrics(case_id, ev_out.plan)
        return c, escalated, case_findings
