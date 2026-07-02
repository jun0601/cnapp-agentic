"""Phase2 end-to-end 러너 — 섬들을 '한 줄'로 잇는다.

    Trivy(스캐너) → Normalizer(정규화) → CorrelationEngine(attack-path) → Orchestrator(엔진) → RAG(설명)

지금까지 각 영역은 자기 `run_demo`만 있었다. 이 러너는 **실 스캐너 출력이 파이프라인을
관통해 엔진 판정·설명까지 도달**하는 걸 한 번에 보여준다(Phase2 = 실 end-to-end 한 줄).

이번 슬라이스의 '새 실(real) 링크 = 스캐너':
  - trivy CLI가 있으면 `--image`로 실제 이미지를 스캔(진짜 CVE).
  - 없으면 실 `trivy image --format json`과 동일 구조의 JSON으로 fallback(배선은 동일 경로).
  - 정규화·상관은 실제 코드(Normalizer/CorrelationEngine) 그대로 관통.
  - 엔진 tool-use와 RAG는 **무비용 Mock**(실 Bedrock+실 S3 tool-use는 Phase1 `engine/run_real.py`에서
    이미 검증 — 여기선 '파이프라인 연결'이 초점이라 비용 0 경로 사용).

실행:
  python -m run_e2e                       # fixture(trivy 불필요) — 무비용
  python -m run_e2e --image <ecr-image>   # 실 trivy 스캔(설치 시). 실패 시 fixture fallback.
"""
from __future__ import annotations

import argparse
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from attackpath.correlation.correlation import CorrelationEngine
from engine.core.contracts import findings_by_id, load_findings
from engine.core.tools import MockToolExecutor
from engine.reasoning.orchestrator import Orchestrator
from pipeline.normalize.normalizer import Normalizer, dedup_findings
from rag.retrieval.answer_gen import RAGAnswerGenerator
from rag.retrieval.retriever import RAGRetriever
from scanners.cspm.cspm import CSPMScanner
from scanners.workload.trivy import TrivyScanner, TrivyScanError

_KEV = "INTERNAL-VULN-KEV-001"

# 실 `trivy image --format json` 출력과 동일 구조(fixture) — trivy 미설치 시 사용.
# ArtifactName에 태그 없음 → resource_id = aws:eks_pod:shop/product (골든 n1과 정합).
_FIXTURE_TRIVY_JSON = {
    "SchemaVersion": 2,
    "ArtifactName": "shop/product",
    "ArtifactType": "container_image",
    "Metadata": {"OS": {"Family": "debian", "Name": "12.5"}},
    "Results": [
        {
            "Target": "shop/product:latest (debian 12.5)",
            "Class": "os-pkgs",
            "Type": "debian",
            "Vulnerabilities": [
                {
                    "VulnerabilityID": "CVE-2024-38856",
                    "PkgName": "openssl",
                    "InstalledVersion": "3.0.11-1~deb12u2",
                    "FixedVersion": "3.0.11-1~deb12u3",
                    "Severity": "CRITICAL",
                    "Title": "OpenSSL: RCE from BIO_new_NDEF [KEV]",
                },
                {
                    "VulnerabilityID": "CVE-2024-6387",
                    "PkgName": "openssh-server",
                    "InstalledVersion": "9.2p1-2+deb12u3",
                    "FixedVersion": "9.8p1",
                    "Severity": "CRITICAL",
                    "Title": "OpenSSH: regreSSHion unauthenticated RCE [KEV]",
                },
            ],
        }
    ],
}


# CSPM 스캐너(준형)가 낼 원본 — golden attack-path의 AWS 설정·데이터·권한 노드 소스.
# (raw, source, source_format). Azure Entra는 진우 ciem 스캐너 미구현이라 mock-findings에서 채움.
_CSPM_RAWS = [
    ({"SchemaVersion": "2018-10-08", "Title": "S3 should block public access",
      "Severity": {"Label": "HIGH"}, "Compliance": {"Status": "FAILED"},
      "ProductFields": {"ControlId": "S3.8"},
      "Resources": [{"Type": "AwsS3Bucket", "Id": "arn:aws:s3:::member-pii-prod"}],
      "UpdatedAt": "2026-07-02T01:00:00Z", "CreatedAt": "2026-07-01T00:00:00Z"},
     "securityhub", "asff"),
    ({"SchemaVersion": "2018-10-08", "Title": "SG should not allow 0.0.0.0/0",
      "Severity": {"Label": "HIGH"}, "Compliance": {"Status": "FAILED"},
      "ProductFields": {"ControlId": "EC2.19"},
      "Resources": [{"Type": "AwsEc2SecurityGroup",
                     "Id": "arn:aws:ec2:ap-northeast-2:123456789012:security-group/sg-0product1234"}],
      "UpdatedAt": "2026-07-02T01:00:00Z", "CreatedAt": "2026-07-01T00:00:00Z"},
     "securityhub", "asff"),
    ({"SchemaVersion": "2018-10-08", "Title": "SensitiveData: PII detected",
      "Severity": {"Label": "HIGH"}, "Compliance": {"Status": "FAILED"},
      "Types": ["Sensitive Data Identifications/PII/SensitiveData:S3Object"],
      "Resources": [{"Type": "AwsS3Bucket", "Id": "arn:aws:s3:::member-pii-prod"}],
      "UpdatedAt": "2026-07-02T01:05:00Z", "CreatedAt": "2026-07-01T00:00:00Z"},
     "macie", "asff"),
    ({"checkID": "iam_inline_policy_allows_privilege_escalation",
      "checkTitle": "Over-privileged IRSA (s3:*)", "status": "FAIL", "severity": "critical",
      "service": "iam", "resourceArn": "arn:aws:iam::123456789012:role/order-irsa",
      "timestamp": "2026-07-02T01:15:00Z", "cloud": "aws"}, "prowler-aws", "prowler-json"),
    ({"checkID": "eks_cluster_secret_encryption",
      "checkTitle": "Plaintext Azure SP credential (order)", "status": "FAIL", "severity": "critical",
      "service": "secretsmanager", "resourceId": "aws:secret_plaintext:shop/order/AZURE_SP_CRED",
      "timestamp": "2026-07-02T01:15:00Z", "cloud": "aws"}, "prowler-aws", "prowler-json"),
]

# Azure Entra findings(진우 ciem 스캐너 미구현 → mock-findings에서)
_AZURE_CONTROLS = {"INTERNAL-ENTRA-SP-CRED-001", "INTERNAL-ENTRA-OVERPRIV-APP-001"}


def _hr(t: str) -> None:
    print("\n" + "=" * 70 + "\n" + t + "\n" + "=" * 70)


def _get_trivy_envelope(scanner: TrivyScanner, image: str | None) -> tuple[dict, str]:
    """(envelope, 모드설명) 반환. --image면 실 스캔 시도, 실패/미지정 시 fixture."""
    if image:
        try:
            env = scanner.scan_image(image)
            return env, "실 trivy 스캔: %s" % image
        except TrivyScanError as e:
            print("  ⚠️ 실 trivy 스캔 실패 → fixture로 fallback: %s" % str(e).splitlines()[0])
    return scanner.scan_from_json(_FIXTURE_TRIVY_JSON, "shop/product:latest"), \
        "fixture(실 trivy 출력 동일 구조 — trivy 미설치 시)"


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase2 end-to-end 러너")
    ap.add_argument("--image", default=None, help="실 trivy 스캔 대상 이미지(설치 시). 없으면 fixture")
    args = ap.parse_args()

    _hr("Phase2 END-TO-END: 스캐너 → 정규화 → 상관 → 엔진 → RAG")

    # ── ① 스캐너 (Trivy) ──────────────────────────────────────────────
    scanner = TrivyScanner()
    envelope, mode = _get_trivy_envelope(scanner, args.image)
    cve_count = sum(len(r.get("Vulnerabilities", [])) for r in envelope["raw_inline"].get("Results", []))
    _hr("① 스캐너 (Trivy) — %s" % mode)
    print("  source=%s / format=%s / CVE %d건" % (envelope["source"], envelope["source_format"], cve_count))
    print("  scan_batch_id=%s" % envelope["scan_batch_id"])

    # ── ② 정규화 (Normalizer) — 실 코드로 envelope → OCSF-lite ─────────
    normalizer = Normalizer()
    scanned = normalizer.normalize(envelope)  # 스캐너발 vuln findings
    _hr("② 정규화 (Normalizer) — envelope → 계약① finding")
    print("  스캐너 finding %d건:" % len(scanned))
    for f in scanned:
        print("   ✓ %s / %s / %s" % (f["control_id"], f["resource_id"], f["sources"][0]))
    scanned_ids = {f["finding_id"] for f in scanned}

    # ── 스캐너 2개(Trivy + CSPM) findings 합류 ─────────────────────────
    # CSPM(SG·IAM·S3·PII·secret) = 준형 CSPMScanner로 실 정규화 관통(scanners/cspm).
    # Azure Entra(SP·App) = 진우 ciem 스캐너 미구현 → mock-findings에서 채움.
    cspm = CSPMScanner()
    cspm_findings = dedup_findings([
        f for raw, src, fmt in _CSPM_RAWS
        for f in normalizer.normalize(cspm.scan_from_json(raw, src, fmt))
    ])
    print("  + CSPM 스캐너 finding %d건(SG·IAM·S3·PII·secret)" % len(cspm_findings))
    azure = [f for f in load_findings() if f.get("control_id") in _AZURE_CONTROLS]
    print("  + Azure Entra finding %d건(mock — ciem 스캐너 미구현)" % len(azure))
    findings = scanned + cspm_findings + azure

    # ── ③ 상관 (CorrelationEngine) — 실 스캐너 2개 findings가 attack-path에 편입 ─────
    paths = CorrelationEngine().correlate(findings)  # findings에 attack_path_id backfill(2-pass)
    _hr("③ 상관 (CorrelationEngine) — R1~R5 → attack-path (소스: Trivy + CSPM 실 정규화)")
    if not paths:
        print("  attack-path 미생성 — 체인 불성립"); return 1
    p = paths[0]
    n1 = p["nodes"][0]
    print("  attack-path %d건 / 노드 %d / 엣지 %d / cross_cloud %d"
          % (len(paths), len(p["nodes"]), len(p["edges"]),
             sum(1 for e in p["edges"] if e.get("cross_cloud"))))
    print("  n1(진입) = %s  ← 스캐너발 CVE finding이 이 노드" % n1["resource_id"])
    n1_from_scan = any(f["resource_id"] == n1["resource_id"] and f["finding_id"] in scanned_ids
                       for f in findings)
    print("  n1이 스캐너 finding에서 왔나: %s" % ("OK ✅" if n1_from_scan else "아님 ⚠️"))

    # ── ④ 엔진 (Orchestrator) — Mock executor(무비용) ─────────────────
    orch = Orchestrator(MockToolExecutor())
    case, escalated, case_findings = orch.run(findings, paths)
    meta = case.get("evidence_meta", {})
    rsn = case.get("reasoning", {})
    _hr("④ 엔진 (Orchestrator, Mock executor — 실 tool-use는 Phase1 run_real에서 검증)")
    print("  triage: 전체 %d건 → escalate %d건" % (len(findings), len(escalated)))
    print("  evidence: read-only 툴 %d회 → verdict=%s (신뢰도 %.0f%%)"
          % (meta.get("tool_calls_count", 0), meta.get("verdict"), meta.get("confidence_score", 0) * 100))
    print("  reasoning: risk_level=%s" % rsn.get("risk_level", "-").upper())

    # ── ⑤ RAG 설명 (mock) — 대표 finding 하나 ─────────────────────────
    fmap = findings_by_id(findings)
    focus = fmap.get(case["finding"]["finding_ids"][0], scanned[0])
    retriever = RAGRetriever(mock=True)
    chunks = retriever.search_by_finding(focus)
    ans = RAGAnswerGenerator(mock=True).generate(focus, chunks, case.get("evidence"))
    _hr("⑤ RAG 설명 (mock) — finding: %s" % focus["control_id"])
    print(ans["explanation"])
    print("\n  rag_refs:", ", ".join(ans["rag_refs"]) or "(없음)")

    # ── ⑥ 검증 ───────────────────────────────────────────────────────
    _hr("⑥ end-to-end 검증")
    ok = (
        len(scanned) >= 1
        and all(f["control_id"] == _KEV for f in scanned)
        and n1_from_scan
        and meta.get("verdict") == "confirmed"
        and bool(ans["explanation"])
    )
    print("  스캐너 CVE → 정규화(KEV) → 상관(n1) → 엔진(confirmed) → RAG(설명): %s"
          % ("OK ✅" if ok else "불일치 ⚠️"))
    print("  => 실 스캐너 출력이 전체 파이프라인을 관통함(엔진 실 tool-use는 Phase1에서 별도 검증).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
