"""attack-path 상관 엔진 데모.

흐름: mock findings (attack_path_id 미설정 상태, 2-pass 시뮬레이션)
  -> CorrelationEngine.correlate()
  -> R1~R5 발화 결과 출력
  -> 골든 정합 검증(mock-attack-paths.json 구조 비교)

실행: 레포 루트에서  python -m attackpath.run_demo
실배포 전환: CorrelationEngine.correlate(rds_findings) 한 줄 교체.
"""
from __future__ import annotations

import copy
import json
import os
import sys

# 윈도우 콘솔(cp949) 대응 — 한글·기호(✅ 등) 출력 시 UnicodeEncodeError 방지.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from attackpath.correlation.correlation import CorrelationEngine

_CONTRACTS = os.path.join(os.path.dirname(__file__), "..", "contracts")


def _load(name: str) -> dict:
    with open(os.path.join(_CONTRACTS, name), encoding="utf-8") as f:
        return json.load(f)


def _hr(title: str) -> None:
    print("\n" + "=" * 68 + "\n" + title + "\n" + "=" * 68)


def main() -> int:
    raw_findings  = _load("mock-findings.json")["findings"]
    golden_paths  = _load("mock-attack-paths.json")["attack_paths"]

    # 2-pass 시뮬레이션: 1차 상관 전 상태 = attack_path_id 없음
    findings = copy.deepcopy(raw_findings)
    for f in findings:
        f["attack_path_id"] = None

    engine = CorrelationEngine()
    paths = engine.correlate(findings)  # 내부에서 backfill도 실행

    # ── ① 상관 결과 요약 ─────────────────────────────────────────
    _hr("① 상관 결과")
    print("전체 finding %d건 -> attack-path %d건 생성" % (len(findings), len(paths)))
    for p in paths:
        cc_count = sum(1 for e in p["edges"] if e.get("cross_cloud"))
        print("  attack_path_id : %s" % p["attack_path_id"])
        print("  severity_id    : %d (Critical)" % p["severity_id"])
        print("  노드 %d개 / 엣지 %d개 / cross_cloud 엣지 %d개"
              % (len(p["nodes"]), len(p["edges"]), cc_count))

    # ── ② 공격 경로 그래프 ───────────────────────────────────────
    _hr("② 공격 경로 그래프")
    if paths:
        p = paths[0]
        print("[노드]")
        for n in p["nodes"]:
            tag = "[AWS]  " if n["cloud"] == "aws" else "[Azure]"
            print("  %s %s  %s  (%s)" % (tag, n["id"], n["resource_id"], n["pillar"]))
        print("\n[엣지]")
        for e in p["edges"]:
            cc = " <<CROSS-CLOUD>>" if e.get("cross_cloud") else ""
            print("  %s --[%s]--> %s%s" % (e["from"], e["type"], e["to"], cc))

    # ── ③ 2-pass backfill 확인 ───────────────────────────────────
    _hr("③ 2-pass backfill (finding -> attack_path_id 역주입)")
    backfilled = [f for f in findings if f.get("attack_path_id")]
    print("역주입 완료: %d건 / 전체 %d건" % (len(backfilled), len(findings)))
    for f in backfilled:
        print("  [%s] %s" % (f["control_id"], f["resource_id"]))

    # ── ④ 골든 정합 검증 ─────────────────────────────────────────
    _hr("④ 골든 정합 검증")
    errs = []  # type: list

    if not paths:
        errs.append("attack-path 미생성")
    else:
        p      = paths[0]
        golden = golden_paths[0]

        if p["attack_path_id"] != golden["attack_path_id"]:
            errs.append("attack_path_id 불일치: %s" % p["attack_path_id"])
        if p["severity_id"] != golden["severity_id"]:
            errs.append("severity_id 불일치: %d != %d" % (p["severity_id"], golden["severity_id"]))
        if len(p["nodes"]) != len(golden["nodes"]):
            errs.append("노드 수 불일치: %d != %d" % (len(p["nodes"]), len(golden["nodes"])))
        if len(p["edges"]) != len(golden["edges"]):
            errs.append("엣지 수 불일치: %d != %d" % (len(p["edges"]), len(golden["edges"])))

        # 4종 엣지 type 전부 발화
        edge_types = {e["type"] for e in p["edges"]}
        expected   = {"lateral_move", "data_exfil", "credential_theft", "identity_takeover"}
        missing    = expected - edge_types
        if missing:
            errs.append("미발화 엣지: %s" % missing)

        # cross_cloud 엣지 존재 확인
        cc_edges = [e for e in p["edges"] if e.get("cross_cloud")]
        if not cc_edges:
            errs.append("cross_cloud 엣지 없음")
        elif cc_edges[0]["type"] != "credential_theft":
            errs.append("cross_cloud 엣지 type 불일치: %s" % cc_edges[0]["type"])

        # AWS/Azure 노드 분포 확인
        aws_nodes   = [n for n in p["nodes"] if n["cloud"] == "aws"]
        azure_nodes = [n for n in p["nodes"] if n["cloud"] == "azure"]
        if len(aws_nodes) != 3 or len(azure_nodes) != 2:
            errs.append("클라우드 분포 불일치: AWS=%d Azure=%d" % (len(aws_nodes), len(azure_nodes)))

        # backfill 최소 확인
        if len(backfilled) < 5:
            errs.append("backfill finding 부족: %d건" % len(backfilled))

    if errs:
        for e in errs:
            print("FAIL: %s" % e)
        return 1

    print("attack_path_id 정합: OK ✅")
    print("노드 5개(AWS 3 + Azure 2) / 엣지 4개: OK ✅")
    print("엣지 4종(lateral_move/data_exfil/credential_theft/identity_takeover): OK ✅")
    print("cross_cloud credential_theft 엣지: OK ✅")
    print("2-pass backfill %d건: OK ✅" % len(backfilled))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
