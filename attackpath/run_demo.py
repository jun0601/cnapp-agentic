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

    _SEV = {1: "Critical", 2: "High", 3: "Medium", 4: "Low", 5: "Info"}

    # ── ① 상관 결과 요약(위험도순 경로 리스트) ─────────────────────
    _hr("① 상관 결과 — 한 posture에서 발견된 독립 경로들(위험도순)")
    print("전체 finding %d건 -> attack-path %d건 생성" % (len(findings), len(paths)))
    for rank, p in enumerate(paths, 1):
        cc_count = sum(1 for e in p["edges"] if e.get("cross_cloud"))
        kind = "크로스클라우드" if cc_count else (
            "AWS 단독" if all(n["cloud"] == "aws" for n in p["nodes"]) else "Azure 단독")
        print("  #%d [%s] %s  노드 %d/엣지 %d (cross_cloud %d)  %s"
              % (rank, _SEV.get(p["severity_id"], "?"), kind,
                 len(p["nodes"]), len(p["edges"]), cc_count, p["attack_path_id"]))

    # ── ② 공격 경로 그래프(전 경로) ──────────────────────────────
    _hr("② 공격 경로 그래프 — 경로별 노드·엣지")
    for rank, p in enumerate(paths, 1):
        print("\n[경로 #%d · %s]" % (rank, _SEV.get(p["severity_id"], "?")))
        for n in p["nodes"]:
            tag = "[AWS]  " if n["cloud"] == "aws" else "[Azure]"
            print("  %s %s  %s  (%s)" % (tag, n["id"], n["resource_id"], n["pillar"]))
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

        # ── 멀티 경로 검증(2026-07-10) ──────────────────────────────
        if len(paths) != 3:
            errs.append("경로 수 불일치: %d != 3" % len(paths))
        ids = [pp["attack_path_id"] for pp in paths]
        if ids and ids[0] != golden["attack_path_id"]:
            errs.append("hero가 최상단(위험도순)이 아님: %s" % ids[0])

        pb = next((pp for pp in paths if pp["attack_path_id"] == "a0000000-0000-4000-8000-000000000002"), None)
        if not pb:
            errs.append("경로 B(AWS 단독 데이터 탈취) 미생성")
        else:
            if any(n["cloud"] != "aws" for n in pb["nodes"]):
                errs.append("경로 B에 비-AWS 노드 존재(AWS 단독이어야 함)")
            if any(e.get("cross_cloud") for e in pb["edges"]):
                errs.append("경로 B에 cross_cloud 엣지 존재")

        pd = next((pp for pp in paths if pp["attack_path_id"] == "a0000000-0000-4000-8000-000000000003"), None)
        if not pd:
            errs.append("경로 D(Azure 단독 신원 장악) 미생성")
        else:
            if any(n["cloud"] != "azure" for n in pd["nodes"]):
                errs.append("경로 D에 비-Azure 노드 존재(Azure 단독이어야 함)")

    if errs:
        for e in errs:
            print("FAIL: %s" % e)
        return 1

    print("경로 3종 생성(hero 크로스클라우드 · AWS 단독 데이터 · Azure 단독 신원): OK ✅")
    print("hero 최상단(위험도순 정렬): OK ✅")
    print("hero attack_path_id 정합 / 노드 5개(AWS 3 + Azure 2) / 엣지 4개: OK ✅")
    print("엣지 4종(lateral_move/data_exfil/credential_theft/identity_takeover): OK ✅")
    print("cross_cloud credential_theft 엣지: OK ✅")
    print("2-pass backfill %d건(각 finding을 최상위 경로에 귀속): OK ✅" % len(backfilled))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
