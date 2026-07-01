"""엔진 능동조사 데모 (준형: Triage + Evidence) — 목업 기반.

흐름: mock findings → ① 트리아지 게이트(소수만 승급) → ② Evidence가 read-only 툴을
스스로 호출해 골든 경로를 조사 → ③ case(계약⑦) 완성 → 검증(스키마·골든 정합).

실행: 레포 루트에서  python -m engine.run_demo
실배포 전환: MockToolExecutor → RealToolExecutor(boto3), 규칙 플래너 → Bedrock LLM.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List

from engine.core import case as case_mod
from engine.core.contracts import load_attack_paths, load_findings
from engine.core.tools import MockToolExecutor
from engine.evidence.evidence import EvidenceAgent
from engine.evidence.triage import triage

GOLDEN_CASE_ID = "c0000000-0000-4000-8000-000000000001"
# Evidence가 조사할 control 순서(데모 서사: 데이터 노출 확인 → 도달 경로 확인)
INVESTIGATION_ORDER = [
    "INTERNAL-S3-PUBLIC-001",
    "INTERNAL-DATA-PII-EXPOSED-001",
    "INTERNAL-IAM-OVERPRIV-001",
]

GOLDEN_HYPOTHESES = [
    "member-pii-prod 버킷이 실제 public이고 PII를 담고 있으면 R4 데이터 탈취가 성립한다",
    "order-irsa의 s3:* 권한이 이 버킷에 닿으면 R2 측면이동 → R4 체인이 연결된다",
]


def _hr(title: str) -> None:
    print("\n" + "=" * 68 + "\n" + title + "\n" + "=" * 68)


def main() -> int:
    findings = load_findings()
    paths = load_attack_paths()
    if not paths:
        print("attack-path 없음 — 종료")
        return 1
    golden_path_id = paths[0]["attack_path_id"]

    # ── ① 트리아지 게이트 — 전체 finding 중 소수만 풀 조사로 승급 ──
    _hr("① 트리아지 게이트 (비용 통제) — 전체 findings")
    escalated: List[dict] = []
    for f in findings:
        t = triage(f)
        if t.escalate:
            escalated.append(f)
    print("전체 %d건 → escalate %d건 (나머지 %d건은 UC1 설명에서 멈춤)"
          % (len(findings), len(escalated), len(findings) - len(escalated)))
    print("→ 풀 조사(Evidence tool-use)는 escalate된 소수만 = Bedrock 비용 통제")

    # ── 골든 case 선정: 골든 경로에 속하고 조사 가능한 control을 가진 finding ──
    case_findings = [
        f for f in escalated
        if f.get("attack_path_id") == golden_path_id and f.get("control_id") in INVESTIGATION_ORDER
    ]
    case_findings.sort(key=lambda f: INVESTIGATION_ORDER.index(f["control_id"]))
    if not case_findings:
        print("골든 경로 조사 대상 finding 없음 — 종료")
        return 1

    # ── case 시작 + 트리아지 요약 ──
    finding_ids = [f["finding_id"] for f in case_findings]
    c = case_mod.new_case(GOLDEN_CASE_ID, finding_ids)
    top = max(triage(f).priority_score for f in case_findings)
    min_sev = min(int(f.get("severity_id", 5)) for f in case_findings)
    triage_reason = ("escalate — attack_path_id!=null(골든 경로) · 최고 severity_id=%d — 게이트 통과(4.4 2-pass)"
                     % min_sev)
    case_mod.set_triage(c, top, True, triage_reason)
    case_mod.set_hypotheses(c, GOLDEN_HYPOTHESES)

    _hr("② Evidence 능동조사 — AI가 스스로 read-only 툴 호출 (챗봇 탈출)")
    print("가설:")
    for h in GOLDEN_HYPOTHESES:
        print("  • " + h)
    agent = EvidenceAgent(MockToolExecutor())
    out = agent.investigate(case_findings)
    print("\n조사 계획(툴 %d개, 계약④ allowlist 내):" % len(out.plan))
    for i, (tool, rid) in enumerate(out.plan, 1):
        print("  %d) %-28s %s" % (i, tool, rid))
    print("\n실행 결과(read-only 호출):")
    for i, e in enumerate(out.evidence, 1):
        print("  [%s] %s\n       └ %s" % (e["ts"], e["tool"], e["result_summary"]))

    case_mod.set_evidence(c, out.evidence, out.tool_calls_count, out.confidence_score, out.verdict)

    _hr("③ 판정 + case 완성")
    print("툴 호출 %d회 · 신뢰도 %.0f%% · 판정 = %s"
          % (out.tool_calls_count, out.confidence_score * 100, out.verdict))
    print("stage = %s (다음: Reasoning = 진우 담당 — 내러티브·최종 리포트)" % c["stage"])

    # ── 검증 ──
    _hr("④ 검증")
    errs = case_mod.validate_shape(c)
    print("case 스키마 정합: %s" % ("OK ✅" if not errs else "FAIL " + str(errs)))
    ok_golden = (out.verdict == "confirmed" and out.tool_calls_count == 4)
    print("골든 정합(4회 호출·confirmed): %s" % ("OK ✅" if ok_golden else "불일치 ⚠️"))

    # 산출 case 저장(디버그/콘솔 연동 확인용)
    out_path = os.path.join(os.path.dirname(__file__), "out_case.json")
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(c, fp, ensure_ascii=False, indent=2)
    print("case 저장 → engine/out_case.json")

    return 0 if (not errs and ok_golden) else 1


if __name__ == "__main__":
    raise SystemExit(main())
