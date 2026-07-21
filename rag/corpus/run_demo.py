"""RAG 코퍼스 적재 데모 — 청크 → 임베딩(mock) → pgvector 적재(dry-run) → 계약⑥ 검증.

실행: 레포 루트에서  python -m rag.corpus.run_demo

흐름:
  1. 코퍼스 내용 로드 — 진우 mock_corpus.all_chunks()(control별 한국어 청크, embedding 없음)
  2. CorpusLoader.load(dry_run) — 각 청크를 mock 임베딩(결정적 1024-dim)해 계약⑥ 청크 완성
  3. 계약⑥ 검증 — embedding[1024]·model const·dim const·metadata.control_id
  4. control-catalog(15종) 커버리지 확인 — 적재 청크가 카탈로그 control을 다 덮는가

실배포 스왑: CorpusLoader(mock=False, pg_dsn=...) → Titan Embed v2 임베딩 + pgvector UPSERT.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from rag.corpus.loader import CorpusLoader, validate_chunk
from rag.retrieval.mock_corpus import all_chunks

_CATALOG_PATH = Path(__file__).parent.parent.parent / "contracts" / "control-catalog.json"


def _catalog_controls() -> set:
    with open(_CATALOG_PATH, encoding="utf-8") as f:
        return set(json.load(f)["controls"].keys())


def _hr(t: str) -> None:
    print("\n" + "=" * 64 + "\n" + t + "\n" + "=" * 64)


def main() -> int:
    _hr("RAG 코퍼스 적재 데모 — 청크 → 임베딩(mock) → pgvector(dry-run) → 계약⑥ 검증")

    seeds = all_chunks()  # 진우 코퍼스 내용(embedding 없음)
    print("코퍼스 내용 로드: 청크 %d개 (진우 mock_corpus)" % len(seeds))

    loader = CorpusLoader(mock=True)
    result = loader.load(seeds, dry_run=True)
    print("임베딩·적재 시뮬: %d개 → dim=%d, model=%s"
          % (result["loaded"], result["dim"], result["model"]))

    # ── 계약⑥ 검증(전 청크) ──────────────────────────────────────────
    _hr("계약⑥ 검증 (embedding[1024]·model const·dim·metadata.control_id)")
    bad = []
    for c in result["chunks"]:
        errs = validate_chunk(c)
        if errs:
            bad.append((c["chunk_id"], errs))
    contract_ok = not bad
    print("전 청크 계약⑥ 정합: %s" % ("OK ✅" if contract_ok else "FAIL ⚠️ " + str(bad[:2])))

    # ── 결정성 확인(같은 텍스트=같은 벡터) ───────────────────────────
    same = loader.embed(seeds[0]["text"]) == loader.embed(seeds[0]["text"])
    print("mock 임베딩 결정성(재현 가능)     : %s" % ("OK ✅" if same else "FAIL ⚠️"))

    # ── control-catalog 커버리지 ─────────────────────────────────────
    _hr("control-catalog(15종) 커버리지")
    catalog = _catalog_controls()
    covered = set(result["controls"])
    missing = catalog - covered
    print("카탈로그 control %d종 / 코퍼스 커버 %d종" % (len(catalog), len(covered)))
    cov_ok = not missing
    print("전 control 커버: %s"
          % ("OK ✅" if cov_ok else "일부 미커버(정상 가능): " + ", ".join(sorted(missing))))

    _hr("전체")
    ok = contract_ok and same
    print("전체(계약⑥ 정합 + 결정성): %s" % ("OK ✅" if ok else "FAIL ⚠️"))
    print("※ 커버리지는 참고(코퍼스 확장 여지) — 계약 정합이 핵심 게이트")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
