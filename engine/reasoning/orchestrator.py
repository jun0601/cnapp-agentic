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
        hypothesis_agent: Optional[object] = None,
        reasoning_agent: Optional[object] = None,
        rag_retriever: Optional[object] = None,
    ) -> None:
        # evidence_agent/hypothesis_agent/reasoning_agent: 템플릿·규칙 플래너(기본) ↔ 실배포
        # LLM 플래너(Bedrock*Agent) 스왑 지점. 셋 다 원본과 동일 인터페이스
        # (generate(findings,paths)->List[str] / investigate(findings)->EvidenceOutput /
        #  analyze(case,findings_map)->dict) 이라 주입만 하면 로직 무변 스왑.
        self.executor = executor or MockToolExecutor()
        self._hyp = hypothesis_agent or HypothesisAgent()
        self._ev = evidence_agent or EvidenceAgent(self.executor)
        self._rsn = reasoning_agent or ReasoningAgent()
        # rag_retriever: 주입되면 Reasoning 결과에 지식베이스 근거(control_id)를 붙인다.
        # None이면 rag_refs=[]로 그대로 진행(무주입 = 기존 동작, CI·목업 무영향).
        # ⚠️ 2026-07-21까지 이 배선 자체가 없어서 계약⑦의 rag_refs가 항상 비어 있었다.
        self._rag = rag_retriever

    def _retrieve_rag_refs(self, case_findings: List[dict]) -> List[str]:
        """조사한 finding들의 지식베이스 근거(control_id)를 모은다 — 중복 제거·입력 순서 유지.

        RAG는 판정의 '보조 설명'이지 판정 자체가 아니므로, 검색이 실패해도(pgvector 미적재·
        Bedrock 오류 등) 케이스 전체를 죽이지 않고 빈 목록으로 강등한다.
        """
        if self._rag is None:
            return []
        refs: List[str] = []
        seen = set()
        try:
            for f in case_findings:
                for chunk in self._rag.search_by_finding(f, top_k=2):
                    ref = (chunk.get("metadata") or {}).get("control_id") or chunk.get("chunk_id")
                    if ref and ref not in seen:
                        seen.add(ref)
                        refs.append(ref)
        except Exception:  # noqa: BLE001 — RAG 실패가 판정을 막으면 안 된다
            return []
        return refs

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
            if not candidate:
                # _INVESTIGATION_ORDER는 hero 경로(크로스클라우드) 전용 조사 순서다 — 다른 경로
                # (aws_data_exfil·azure_identity)의 control은 여기 없어 위 필터가 항상 0건이 된다.
                # 순서를 강제할 이유가 없는(대개 1~2건) 경로이므로, 이 경로 소속 escalated
                # finding을 순서 없이 그대로 조사 대상으로 삼는다(2026-07-21).
                candidate = [
                    f for f in escalated if f.get("attack_path_id") == golden_path_id
                ]
        else:
            candidate = escalated[:3]  # fallback: 상위 3건

        if not candidate:
            raise ValueError("조사 대상 finding 없음 — 종료")

        case_findings = candidate  # type: List[dict]
        finding_ids = [f["finding_id"] for f in case_findings]
        c = case_mod.new_case(case_id, finding_ids)

        top_score = max(triage(f).priority_score for f in case_findings)
        min_sev = min(int(f.get("severity_id", 5)) for f in case_findings)
        # 승급 사유는 실제 조건에서 도출한다 — 옛 코드는 "attack_path_id!=null(골든 경로)"로
        # 하드코딩돼 있어, 경로에 안 붙고 severity만으로 승급된 case에도 틀린 사유가 찍혔다.
        drivers = []
        if golden_path_id:
            drivers.append("attack_path_id!=null(경로 소속)")
        if min_sev <= 2:
            drivers.append("severity_id=%d(High↑)" % min_sev)
        case_mod.set_triage(
            c, top_score, True,
            "escalate — " + " · ".join(drivers or ["게이트 통과"]),
        )

        # ── ② Hypothesis ──────────────────────────────────────────
        hypotheses = self._hyp.generate(escalated, paths)
        # last_tokens/model_label: mock(HypothesisAgent)·real(BedrockHypothesisAgent) 둘 다
        # 동일 이름 속성을 노출해서(계약 밖 부가정보) getattr 하나로 통일 처리(2026-07-10).
        hyp_in, hyp_out = getattr(self._hyp, "last_tokens", (0, 0))
        case_mod.set_hypotheses(
            c, hypotheses, tokens=hyp_in + hyp_out,
            model=getattr(self._hyp, "model_label", "template"),
        )

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
        rsn_in, rsn_out = getattr(self._rsn, "last_tokens", (0, 0))
        case_mod.set_reasoning(
            c, rsn["narrative"], rsn["risk_level"], rsn["recommended_actions"],
            tokens=rsn_in + rsn_out, model=getattr(self._rsn, "model_label", "template"),
            rag_refs=self._retrieve_rag_refs(case_findings),
        )

        # EMF 비용 지표는 케이스 1건 전체(Hypothesis+Evidence+Reasoning 3스테이지 합)를 반영—
        # 2026-07-10 이전엔 Evidence만 집계돼 실제 Bedrock 비용을 과소산정하고 있었음.
        _emit_case_metrics(
            c, len(findings), len(escalated), (time.time() - t0) * 1000,
            input_tokens=hyp_in + ev_out.input_tokens + rsn_in,
            output_tokens=hyp_out + ev_out.output_tokens + rsn_out,
        )
        _emit_tool_usage_metrics(case_id, ev_out.plan)
        return c, escalated, case_findings
