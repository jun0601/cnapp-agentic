#!/usr/bin/env python3
"""contracts/ 정합 검증 — CI 게이트 (target-app-design §2.1).

JSON 유효성 + 의미 정합 7-assert(a~g)를 검사한다. json.load가 못 잡는 '의미 불일치'를
여기서 막는다. 실패 시 exit 1 → GitHub Actions가 머지 차단.

asserts:
  (a) finding.pillar == catalog[control_id].pillar
  (b) resource_id 2번째 세그먼트 == resource_type        (4.4.1a 캐논)
  (c) 모든 attack-path node.resource_id 가 실 finding에 grounding(≥1, 멀티경로 공유 노드 허용)
  (d) dedup_key == resource_id|control_id
보너스:
  (e) finding.control_id 가 control-catalog 에 존재
  (f) mock-cases finding_ids 존재 · evidence tool 이 evidence-allowlist 안
"""
import json
import sys
from pathlib import Path

# 윈도우 콘솔(cp949) 대응 — 한글·em-dash 등 출력 시 UnicodeEncodeError 방지(다른 run_demo.py와 동일 패턴).
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

HERE = Path(__file__).resolve().parent
errors = []


def load(name):
    try:
        return json.loads((HERE / name).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        errors.append(f"[json] {name} 파싱 실패: {e}")
        return None


def main():
    catalog_doc = load("control-catalog.json")
    mf_doc = load("mock-findings.json")
    ap_doc = load("mock-attack-paths.json")
    mc_doc = load("mock-cases.json")
    al_doc = load("evidence-allowlist.json")
    # 스키마 파일도 파싱 유효성만 확인
    for s in [
        "finding.schema.json", "case.schema.json", "attack-path.schema.json",
        "ingest-envelope.schema.json", "rag-chunk.schema.json",
    ]:
        load(s)

    if errors:  # 파싱 단계에서 깨지면 더 진행 불가
        report()

    catalog = catalog_doc["controls"]
    findings = mf_doc["findings"]
    paths = ap_doc["attack_paths"]
    allow = set(al_doc["aws"])

    for f in findings:
        fid = f["finding_id"]
        cid = f["control_id"]
        # (e) control 존재
        if cid not in catalog:
            errors.append(f"[e] {fid}: control_id '{cid}' 가 control-catalog 에 없음")
        else:
            # (a) pillar 일치
            cat_pillar = catalog[cid]["pillar"]
            if f["pillar"] != cat_pillar:
                errors.append(f"[a] {fid}: finding.pillar '{f['pillar']}' != catalog '{cat_pillar}' ({cid})")
        # (b) resource_id 2번째 세그먼트 == resource_type
        seg = f["resource_id"].split(":")
        if len(seg) < 3 or seg[1] != f["resource_type"]:
            errors.append(f"[b] {fid}: resource_id type 세그먼트 '{seg[1] if len(seg) > 1 else '?'}' != resource_type '{f['resource_type']}'")
        # (d) dedup_key
        expect = f"{f['resource_id']}|{f['control_id']}"
        if f["dedup_key"] != expect:
            errors.append(f"[d] {fid}: dedup_key '{f['dedup_key']}' != '{expect}'")

    # (c) 모든 attack-path 노드는 실제 finding에 grounding돼 있어야 함(resource_id 기준 ≥1)
    # 멀티경로(2026-07-10): 한 finding이 여러 경로에 참여할 수 있는데 attack_path_id는 단일값이라
    # 최상위 경로 하나에만 태깅된다(correlation._backfill_multi) → "해당 path에 태깅된 finding"을
    # 요구하면 공유 노드가 오탐. 노드가 실 finding에 근거하는지(grounding)만 검사한다.
    for p in paths:
        pid = p["attack_path_id"]
        for n in p["nodes"]:
            rid = n["resource_id"]
            hits = [f for f in findings if f["resource_id"] == rid]
            if not hits:
                errors.append(f"[c] attack-path {pid} node '{n['id']}'({rid}) 에 대응 finding 없음(grounding 실패)")
        # 엣지 노드 참조 유효성
        node_ids = {n["id"] for n in p["nodes"]}
        for e in p["edges"]:
            if e["from"] not in node_ids or e["to"] not in node_ids:
                errors.append(f"[c] attack-path {pid} edge 노드참조 오류: {e}")

    # (f) mock-cases
    fids = {f["finding_id"] for f in findings}
    for c in mc_doc["cases"]:
        for i in c["finding"].get("finding_ids", []):
            if i not in fids:
                errors.append(f"[f] case {c['case_id']}: finding_id '{i}' 미존재")
        for ev in c.get("evidence", []):
            if ev["tool"] not in allow:
                errors.append(f"[f] case {c['case_id']}: evidence tool '{ev['tool']}' allowlist 외")

    # (g) 임베딩 모델 상수가 구현 3곳에서 일치하는가 — 계약⑥ embedding_model const
    assert_embedding_model_consistency()

    report()


# 계약⑥ embedding_model을 실제로 참조하는 구현들(적재 1 + 검색 2).
# ⚠️ RAG 검색은 폴리글랏 설계상 Python(엔진용)·TypeScript(콘솔 /chat용) 두 벌로 존재한다.
#    둘이 다른 모델을 쓰면 벡터 공간이 달라져 **에러 없이 검색 결과만 엉뚱해진다**(조용한 실패).
#    그래서 "같은 상수를 쓰는가"를 CI가 텍스트 수준에서라도 강제한다.
_EMBED_MODEL_SITES = [
    ("rag/corpus/loader.py", r'EMBEDDING_MODEL\s*=\s*"([^"]+)"'),          # 적재(Python)
    ("apps/console-backend/src/data.ts", r"EMBED_MODEL\s*=\s*'([^']+)'"),  # 검색(TypeScript, /chat)
]


def assert_embedding_model_consistency() -> None:
    """적재·검색 구현이 계약⑥의 embedding_model const와 같은 모델을 쓰는지 확인.

    (검색 Python판 rag/retrieval/retriever.py는 자체 상수 없이 CorpusLoader.embed()에
     위임하므로 loader.py 하나만 보면 된다 — 위임 구조가 깨지면 아래 import 검사에서 걸린다.)
    """
    import re

    schema = load("rag-chunk.schema.json")
    if not schema:
        return
    want = schema["properties"]["embedding_model"]["const"]
    root = HERE.parent  # 레포 루트(contracts/의 상위)

    for rel, pattern in _EMBED_MODEL_SITES:
        path = root / rel
        if not path.is_file():
            errors.append(f"[g] 임베딩 모델 참조 파일 없음: {rel}")
            continue
        m = re.search(pattern, path.read_text(encoding="utf-8"))
        if not m:
            errors.append(f"[g] {rel}: 임베딩 모델 상수를 못 찾음(리팩터로 이름이 바뀌었나?)")
        elif m.group(1) != want:
            errors.append(
                f"[g] {rel}: embedding_model '{m.group(1)}' != 계약⑥ const '{want}' "
                f"— 적재·검색 벡터가 안 맞아 검색이 조용히 깨진다"
            )

    # Python 검색부가 적재부에 위임하는 구조 자체를 검사(자체 모델 상수를 새로 들이면 드리프트 시작).
    retr = root / "rag/retrieval/retriever.py"
    if retr.is_file() and "from rag.corpus.loader import CorpusLoader" not in retr.read_text(encoding="utf-8"):
        errors.append("[g] rag/retrieval/retriever.py가 CorpusLoader에 임베딩을 위임하지 않음 — 모델 드리프트 위험")


def report():
    if errors:
        print(f"FAIL — {len(errors)} 건:")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("OK — contracts 정합 검증 통과 (a~g 7-assert + json + control + case)")
    sys.exit(0)


if __name__ == "__main__":
    main()
