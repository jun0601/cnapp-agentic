"""RAG 검색·답변 데모 — finding → 청크 검색 → 한국어 설명 생성.

실행: 레포 루트에서  python -m rag.retrieval.run_demo

무슨 일이 일어나는가:
  1. mock finding 3건 준비 (골든 경로 control_id 커버)
  2. RAGRetriever.search_by_finding() → 관련 청크 검색 (계약⑥)
  3. RAGAnswerGenerator.generate() → 한국어 설명 + rag_refs 생성
  4. 골든 정합 검증:
     - 검색 결과가 해당 control_id의 청크인가
     - rag_refs가 chunk_id 목록으로 채워졌는가
     - explanation에 finding 정보(등급·리소스)가 포함됐는가
     - 코퍼스가 14개 전체 control_id를 커버하는가

실배포 스왑:
  RAGRetriever(mock=False) + RAGAnswerGenerator(mock=False)
  → Titan Embed v2 + pgvector + Bedrock Claude Sonnet 호출
"""
from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from rag.retrieval.answer_gen import RAGAnswerGenerator
from rag.retrieval.mock_corpus import all_chunks, covered_controls
from rag.retrieval.retriever import RAGRetriever

# ── mock finding 3건 (골든 경로 핵심 control) ─────────────────────────────
MOCK_FINDINGS = [
    {
        "finding_id": "f0000001-0000-4000-8000-000000000001",
        "cloud": "aws",
        "resource_id": "aws:eks_pod:shop/product",
        "resource_type": "eks_pod",
        "pillar": "vuln",
        "control_id": "INTERNAL-VULN-KEV-001",
        "title": "KEV-listed CVE in container image (CVE-2024-38856)",
        "severity_id": 1,
        "status": "open",
        "sources": ["trivy:CVE-2024-38856"],
        "dedup_key": "aws:eks_pod:shop/product|INTERNAL-VULN-KEV-001|CVE-2024-38856",
        "ai_status": "pending",
        "first_seen": "2026-07-01T00:00:00Z",
        "last_seen": "2026-07-02T00:00:00Z",
    },
    {
        "finding_id": "f0000002-0000-4000-8000-000000000002",
        "cloud": "aws",
        "resource_id": "aws:s3_bucket:member-pii-prod",
        "resource_type": "s3_bucket",
        "pillar": "cspm",
        "control_id": "INTERNAL-S3-PUBLIC-001",
        "title": "S3 bucket allows public access",
        "severity_id": 1,
        "status": "open",
        "sources": ["securityhub:S3.8"],
        "dedup_key": "aws:s3_bucket:member-pii-prod|INTERNAL-S3-PUBLIC-001",
        "ai_status": "pending",
        "first_seen": "2026-07-01T00:00:00Z",
        "last_seen": "2026-07-02T00:00:00Z",
    },
    {
        "finding_id": "f0000003-0000-4000-8000-000000000003",
        "cloud": "azure",
        "resource_id": "azure:app_registration:cnapp-agentic-overpriv-app",
        "resource_type": "app_registration",
        "pillar": "ciem",
        "control_id": "INTERNAL-ENTRA-OVERPRIV-APP-001",
        "title": "Over-privileged Entra App Registration (Directory.ReadWrite.All)",
        "severity_id": 1,
        "status": "open",
        "sources": ["prowler:entra_id_app_overprivileged"],
        "dedup_key": "azure:app_registration:cnapp-agentic-overpriv-app|INTERNAL-ENTRA-OVERPRIV-APP-001",
        "ai_status": "pending",
        "first_seen": "2026-07-01T00:00:00Z",
        "last_seen": "2026-07-02T00:00:00Z",
    },
]

# mock evidence (에이전트 조사 결과 — 엔진 Evidence 단계 산출물 모방)
MOCK_EVIDENCE = [
    {
        "tool": "s3:GetBucketPublicAccessBlock",
        "resource_id": "aws:s3_bucket:member-pii-prod",
        "result_summary": "BlockPublicAcls=false — 퍼블릭 ACL 허용 상태",
        "ts": "2026-07-02T10:00:00Z",
    },
    {
        "tool": "s3:GetBucketPolicy",
        "resource_id": "aws:s3_bucket:member-pii-prod",
        "result_summary": "Principal=* 버킷 정책 발견 — 인터넷 전체 공개",
        "ts": "2026-07-02T10:00:01Z",
    },
]


def _hr(title: str) -> None:
    print("\n" + "=" * 68 + "\n" + title + "\n" + "=" * 68)


def main() -> int:
    retriever = RAGRetriever(mock=True)
    generator = RAGAnswerGenerator(mock=True)

    _hr("RAG 검색·답변 데모 — finding → 청크 검색 → 한국어 설명")

    results: list[dict] = []

    # ── 1단계: finding별 검색 + 설명 생성 ────────────────────────────────
    _hr("[1단계] finding → 청크 검색 → 설명 생성")

    for i, finding in enumerate(MOCK_FINDINGS, 1):
        print("\n--- finding %d: %s ---" % (i, finding["control_id"]))

        chunks = retriever.search_by_finding(finding, top_k=2)
        print("  검색된 청크 수: %d건" % len(chunks))
        for c in chunks:
            print("  [%s] %s..." % (c["chunk_id"][:8], c["text"][:60]))

        # finding 2(S3)는 evidence도 함께 전달
        ev = MOCK_EVIDENCE if finding["control_id"] == "INTERNAL-S3-PUBLIC-001" else None
        out = generator.generate(finding, chunks, evidence=ev)

        print("\n  설명 (앞 200자):")
        print("  " + out["explanation"][:200].replace("\n", "\n  "))
        print("\n  rag_refs:", out["rag_refs"])
        print("  model:   ", out["model_trace"]["model"])

        results.append({"finding": finding, "chunks": chunks, "output": out})

    # ── 2단계: search_multi 검증 ──────────────────────────────────────────
    _hr("[2단계] search_multi — 여러 finding 일괄 검색")
    multi = retriever.search_multi(MOCK_FINDINGS, top_k_each=2)
    for fid, chunks in multi.items():
        print("  finding_id=%s... → %d청크" % (fid[:8], len(chunks)))

    # ── 3단계: 코퍼스 커버리지 확인 ──────────────────────────────────────
    _hr("[3단계] 코퍼스 커버리지 확인")
    covered = covered_controls()
    total_chunks = len(all_chunks())
    print("  커버된 control_id: %d개" % len(covered))
    print("  전체 청크 수:      %d개" % total_chunks)
    for ctrl in covered:
        print("  ✓ " + ctrl)

    # ── 4단계: 골든 정합 검증 ────────────────────────────────────────────
    _hr("[4단계] 골든 정합 검증")
    checks = []

    # (a) 각 finding 검색 결과의 control_id가 요청한 것과 일치
    ctrl_match = all(
        r["chunks"][0]["metadata"]["control_id"] == r["finding"]["control_id"]
        for r in results
        if r["chunks"]
    )
    checks.append(("검색된 청크의 control_id가 finding.control_id와 일치", ctrl_match))

    # (b) rag_refs가 채워졌는가
    rag_refs_ok = all(len(r["output"]["rag_refs"]) > 0 for r in results)
    checks.append(("모든 finding에 rag_refs 1개 이상", rag_refs_ok))

    # (c) explanation에 finding 등급 레이블이 포함됐는가
    exp_ok = all(
        "Critical" in r["output"]["explanation"] or "High" in r["output"]["explanation"]
        for r in results
    )
    checks.append(("explanation에 severity 레이블 포함", exp_ok))

    # (d) explanation에 resource_id가 포함됐는가
    resource_ok = all(
        r["finding"]["resource_id"].split(":")[-1] in r["output"]["explanation"]
        for r in results
    )
    checks.append(("explanation에 resource 식별자 포함", resource_ok))

    # (e) S3 finding에 evidence 내용이 반영됐는가
    s3_result = next(
        r for r in results if r["finding"]["control_id"] == "INTERNAL-S3-PUBLIC-001"
    )
    ev_reflected = "에이전트 조사" in s3_result["output"]["explanation"]
    checks.append(("S3 finding 설명에 evidence 조사 내용 반영", ev_reflected))

    # (f) 코퍼스가 14개 control 전체 커버 (control-catalog.json 기준)
    import json, os as _os
    _cat_path = _os.path.join(
        _os.path.dirname(__file__), "..", "..", "contracts", "control-catalog.json"
    )
    with open(_cat_path, encoding="utf-8") as _f:
        _catalog = json.load(_f)
    catalog_count = len(_catalog["controls"])
    corpus_coverage = len(covered_controls()) == catalog_count
    checks.append(("코퍼스가 카탈로그 14개 control 전부 커버", corpus_coverage))

    all_ok = True
    for label, ok in checks:
        status = "OK ✅" if ok else "FAIL ⚠️"
        print("  %s  %s" % (status, label))
        if not ok:
            all_ok = False

    print("\n전체:", "OK ✅" if all_ok else "FAIL ⚠️")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
