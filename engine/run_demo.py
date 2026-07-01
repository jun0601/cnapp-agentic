"""엔진 전체 루프 데모 — Orchestrator 기반.

흐름: mock findings
  → ① Triage 게이트(비용 통제)
  → ② Hypothesis(가설 자동 생성)
  → ③ Evidence(read-only 툴 자가 호출, 챗봇 탈출)
  → ④ Reasoning(내러티브·위험수준·권고사항)
  → ⑤ 검증(스키마·골든 정합)

실행: 레포 루트에서  python -m engine.run_demo
실배포 전환: Orchestrator(executor=RealToolExecutor()) 한 줄 교체.
"""
from __future__ import annotations

import json
import os

from engine.core import case as case_mod
from engine.core.contracts import load_attack_paths, load_findings
from engine.core.tools import MockToolExecutor
from engine.orchestrator.orchestrator import Orchestrator


def _hr(title: str) -> None:
    print("\n" + "=" * 68 + "\n" + title + "\n" + "=" * 68)


def main() -> int:
    findings = load_findings()
    paths = load_attack_paths()
    if not paths:
        print("attack-path 없음 — 종료")
        return 1

    orch = Orchestrator(MockToolExecutor())

    try:
        c, escalated, case_findings = orch.run(findings, paths)
    except ValueError as e:
        print(str(e))
        return 1

    # ── ① Triage ──────────────────────────────────────────────────
    _hr("① 트리아지 게이트 (비용 통제)")
    print("전체 %d건 → escalate %d건 (나머지 %d건은 UC1 설명에서 멈춤)"
          % (len(findings), len(escalated), len(findings) - len(escalated)))
    print("→ 풀 조사(Evidence tool-use)는 escalate 소수만 = Bedrock 비용 통제")

    # ── ② Hypothesis ──────────────────────────────────────────────
    _hr("② Hypothesis — 에이전트가 가설 자동 생성")
    for h in c.get("hypotheses", []):
        print("  • " + h)

    # ── ③ Evidence ────────────────────────────────────────────────
    _hr("③ Evidence — AI가 스스로 read-only 툴 호출 (챗봇 탈출)")
    meta = c.get("evidence_meta", {})
    print("툴 %d회 호출 (계약④ allowlist 내):" % meta.get("tool_calls_count", 0))
    for e in c.get("evidence", []):
        print("  [%s] %s\n       └ %s" % (e["ts"], e["tool"], e["result_summary"]))

    # ── ④ Reasoning ───────────────────────────────────────────────
    _hr("④ Reasoning — 내러티브 + 위험 수준 + 권고사항")
    r = c.get("reasoning", {})
    print("위험 수준: %s" % r.get("risk_level", "-").upper())
    print("\n내러티브:")
    print("  " + r.get("narrative", ""))
    print("\n권고사항:")
    for a in r.get("recommended_actions", []):
        print("  • " + a)

    # ── ⑤ 검증 ───────────────────────────────────────────────────
    _hr("⑤ 검증")
    errs = case_mod.validate_shape(c)
    print("case 스키마: %s" % ("OK ✅" if not errs else "FAIL " + str(errs)))
    ok_golden = (
        meta.get("verdict") == "confirmed"
        and meta.get("tool_calls_count") == 4
        and c.get("stage") == "reasoning"
    )
    print("골든 정합(4회 호출·confirmed·stage=reasoning): %s"
          % ("OK ✅" if ok_golden else "불일치 ⚠️"))

    out_path = os.path.join(os.path.dirname(__file__), "out_case.json")
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(c, fp, ensure_ascii=False, indent=2)
    print("case 저장 → engine/out_case.json")

    return 0 if (not errs and ok_golden) else 1


if __name__ == "__main__":
    raise SystemExit(main())
