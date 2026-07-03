"""워크로드 스캐너 데모 — Trivy 이미지 스캔 + kube-bench KSPM → ingest-envelope → OCSF-lite finding.

실행: 레포 루트에서  python -m scanners.workload.run_demo

무슨 일이 일어나는가:
  [Trivy]
    1. mock Trivy JSON 3건 (product 이미지 CVE 목록) 을 미리 준비
    2. TrivyScanner.scan_from_json() 으로 계약⑤ ingest-envelope 조립
    3. Normalizer.normalize(envelope) 으로 계약① finding[] 변환
    4. 골든 정합 검증(control_id·severity·resource_id·dedup)
  [kube-bench]
    1. mock kube-bench JSON(product·member 파드 대상) 을 미리 준비
    2. KubeBenchScanner.scan_from_json() 으로 계약⑤ ingest-envelope 조립
       (source="kube-bench", source_format="custom")
    3. Normalizer.normalize(envelope) 으로 계약① finding[] 변환
    4. 골든 정합 검증(control_id·resource_id·pillar) + PASS→remediated 상태 전환 확인

실배포 스왑:
  TrivyScanner.scan_image("123456789.dkr.ecr.ap-northeast-2.amazonaws.com/product:latest")
  KubeBenchScanner.scan_cluster("shop/product")  — 둘 다 CLI/클러스터 있으면 실 스캔.
  봉투화·정규화 로직은 무변.
"""
from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from pipeline.normalize.normalizer import Normalizer
from scanners.workload.kube_bench import KubeBenchScanner
from scanners.workload.trivy import TrivyScanner

# ── mock Trivy JSON (실 trivy 없이 end-to-end 검증용) ─────────────────
# 형식: trivy image --format json 출력과 동일한 구조
# ArtifactName에 태그를 붙이지 않음 → resource_id = aws:eks_pod:shop/product (깔끔)
MOCK_TRIVY_JSON = {
    "SchemaVersion": 2,
    "ArtifactName": "shop/product",
    "ArtifactType": "container_image",
    "Metadata": {
        "ImageID": "sha256:deadbeef00000000000000000000000000000000000000000000000000000000",
        "OS": {"Family": "debian", "Name": "12.5"},
    },
    "Results": [
        {
            "Target": "shop/product:latest (debian 12.5)",
            "Class": "os-pkgs",
            "Type": "debian",
            "Vulnerabilities": [
                # ── f1 골든 finding: KEV CVE ──────────────────────────
                {
                    "VulnerabilityID": "CVE-2024-38856",
                    "PkgName": "openssl",
                    "InstalledVersion": "3.0.11-1~deb12u2",
                    "FixedVersion": "3.0.11-1~deb12u3",
                    "Severity": "CRITICAL",
                    "Title": "OpenSSL: Possible remote code execution from BIO_new_NDEF [KEV]",
                    "References": [
                        "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
                    ],
                },
                # ── 추가 KEV CVE (골든 product 이미지 현실감) ──────────
                {
                    "VulnerabilityID": "CVE-2024-6387",
                    "PkgName": "openssh-server",
                    "InstalledVersion": "9.2p1-2+deb12u3",
                    "FixedVersion": "9.8p1",
                    "Severity": "CRITICAL",
                    "Title": "OpenSSH: regreSSHion — unauthenticated RCE [KEV]",
                    "References": [
                        "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
                    ],
                },
                # ── HIGH CVE ──────────────────────────────────────────
                {
                    "VulnerabilityID": "CVE-2023-44487",
                    "PkgName": "nginx",
                    "InstalledVersion": "1.23.3-1~bookworm",
                    "FixedVersion": "1.25.3",
                    "Severity": "HIGH",
                    "Title": "HTTP/2 Rapid Reset Attack (DDOS amplification)",
                },
            ],
        }
    ],
}


# ── mock kube-bench JSON (실 kubectl/클러스터 없이 end-to-end 검증용) ──
# 형식: kube-bench --json 출력과 동일한 구조(Controls[].controls.tests[].results[])
# ⚠️ 실 kube-bench는 파드를 지목하지 않음 — target_resource는 스캐너가 얹어줌
# (kube_bench.py 모듈 docstring의 모델링 단순화 참고).
def _kube_bench_result(test_number: str, test_desc: str, status: str) -> dict:
    return {
        "Controls": [
            {
                "controls": {
                    "id": "5",
                    "version": "cis-1.24",
                    "text": "Kubernetes Policies",
                    "node_type": "policies",
                    "tests": [
                        {
                            "section": "5.2",
                            "desc": "Pod Security Standards",
                            "results": [
                                {
                                    "test_number": test_number,
                                    "test_desc": test_desc,
                                    "status": status,
                                    "scored": True,
                                }
                            ],
                        }
                    ],
                }
            }
        ]
    }


# f2 골든 finding: product 파드 privileged 컨테이너
MOCK_KUBE_BENCH_PRODUCT = _kube_bench_result(
    "5.2.5", "Minimize the admission of privileged containers", "FAIL"
)
# f13 골든 finding: member 파드 root 사용자 실행
MOCK_KUBE_BENCH_MEMBER = _kube_bench_result(
    "5.2.6", "Minimize the admission of root containers", "FAIL"
)
# 골든에는 없는 추가 검증용: order 파드는 점검 통과 → remediated 상태 전환 확인
MOCK_KUBE_BENCH_ORDER_PASS = _kube_bench_result(
    "5.2.5", "Minimize the admission of privileged containers", "PASS"
)


def _hr(title: str) -> None:
    print("\n" + "=" * 64 + "\n" + title + "\n" + "=" * 64)


def _run_trivy_demo() -> bool:
    scanner = TrivyScanner()
    normalizer = Normalizer()

    _hr("[Trivy] 워크로드 취약점 스캐너 — trivy-json → OCSF-lite finding")

    # ── 1단계: Trivy JSON → ingest-envelope ──────────────────────────
    print("\n[1단계] TrivyScanner.scan_from_json() → 계약⑤ ingest-envelope 조립")
    envelope = scanner.scan_from_json(MOCK_TRIVY_JSON, "shop/product:latest")
    print("  envelope_id   :", envelope["envelope_id"])
    print("  source        :", envelope["source"])
    print("  source_format :", envelope["source_format"])
    print("  scan_batch_id :", envelope["scan_batch_id"])
    print("  raw CVE 수    :", len(
        MOCK_TRIVY_JSON["Results"][0].get("Vulnerabilities", [])
    ), "건")

    # ── 2단계: envelope → finding[] ───────────────────────────────────
    print("\n[2단계] Normalizer.normalize(envelope) → 계약① finding[]")
    findings = normalizer.normalize(envelope)
    print(f"  finding {len(findings)}건 생성\n")

    for f in findings:
        sev_label = {1: "CRITICAL", 2: "HIGH", 3: "MEDIUM", 4: "LOW", 5: "INFO"}.get(
            f["severity_id"], "?"
        )
        cves = ", ".join(s.replace("trivy:", "") for s in f["sources"])
        print(f"  ✓ [{sev_label}] {f['control_id']}")
        print(f"    cve(s)     : {cves}")
        print(f"    resource   : {f['resource_id']}")
        print(f"    pillar     : {f['pillar']}")
        print(f"    dedup_key  : {f['dedup_key']}")
        print()

    # ── 3단계: 골든 정합 검증 ─────────────────────────────────────────
    _hr("[Trivy] 골든 정합 검증")

    checks = []

    # (a) 모든 finding이 INTERNAL-VULN-KEV-001에 매핑됐는가
    all_vuln = all(f["control_id"] == "INTERNAL-VULN-KEV-001" for f in findings)
    checks.append(("모든 CVE → INTERNAL-VULN-KEV-001 매핑", all_vuln))

    # (b) UNKNOWN control 없음
    no_unknown = not any(f["control_id"] == "INTERNAL-UNKNOWN-001" for f in findings)
    checks.append(("INTERNAL-UNKNOWN-001 없음", no_unknown))

    # (c) resource_id 캐논 형식 (aws:eks_pod:shop/product)
    canon_ok = all(f["resource_id"] == "aws:eks_pod:shop/product" for f in findings)
    checks.append(("resource_id 캐논 (aws:eks_pod:shop/product)", canon_ok))

    # (d) CRITICAL CVE → severity_id = 1 (sources 안 어딘가에 있으면 됨 — dedup 후 순서 무보장)
    critical_ok = any(
        f["severity_id"] == 1 and any("CVE-2024-38856" in s for s in f["sources"])
        for f in findings
    )
    checks.append(("CVE-2024-38856 CRITICAL → severity_id=1", critical_ok))

    # (e) pillar = "vuln"
    pillar_ok = all(f["pillar"] == "vuln" for f in findings)
    checks.append(("pillar = vuln", pillar_ok))

    # (f) 계약① dedup: 같은 이미지+같은 control(KEV-001)이면 CVE 3건이 finding 1건으로 합쳐지고
    # sources에 CVE 3개가 전부 누적됨(2026-07-03 — 이전엔 dedup_key에 CVE를 넣어 3건으로 안
    # 합쳐졌던 게 계약①·골든 mock-findings.json의 "이미지당 1건" 의도와 어긋난 버그였음).
    count_ok = len(findings) == 1 and len(findings[0]["sources"]) == 3
    checks.append(("finding 1건으로 dedup (CVE 3건은 sources에 누적)", count_ok))

    all_ok = True
    for label, ok in checks:
        status = "OK ✅" if ok else "FAIL ⚠️"
        print(f"  {status}  {label}")
        if not ok:
            all_ok = False

    return all_ok


def _run_kube_bench_demo() -> bool:
    scanner = KubeBenchScanner()
    normalizer = Normalizer()

    _hr("[kube-bench] KSPM 스캐너 — CIS 벤치마크 → OCSF-lite finding")

    # ── 1단계: 파드 2개(product·member) 대상 스캔 ────────────────────
    print("\n[1단계] KubeBenchScanner.scan_from_json() → 계약⑤ ingest-envelope 조립")
    env_product = scanner.scan_from_json(MOCK_KUBE_BENCH_PRODUCT, "shop/product")
    env_member = scanner.scan_from_json(MOCK_KUBE_BENCH_MEMBER, "shop/member")
    env_order_pass = scanner.scan_from_json(MOCK_KUBE_BENCH_ORDER_PASS, "shop/order")
    print("  source        :", env_product["source"])
    print("  source_format :", env_product["source_format"])
    print("  scan_batch_id(product):", env_product["scan_batch_id"])

    # ── 2단계: envelope → finding[] ───────────────────────────────────
    print("\n[2단계] Normalizer.normalize(envelope) → 계약① finding[]")
    f_product = normalizer.normalize(env_product)
    f_member = normalizer.normalize(env_member)
    f_order = normalizer.normalize(env_order_pass)
    all_findings = f_product + f_member + f_order
    print(f"  finding {len(all_findings)}건 생성(product·member·order 각 1)\n")

    for f in all_findings:
        print(f"  ✓ [{f['status']}] {f['control_id']}  ({f['resource_id']})")
        print(f"    title      : {f['title']}")
        print(f"    pillar     : {f['pillar']}  severity_id: {f['severity_id']}")
        print(f"    dedup_key  : {f['dedup_key']}")
        print()

    # ── 3단계: 골든 정합 검증 ─────────────────────────────────────────
    _hr("[kube-bench] 골든 정합 검증")

    checks = []

    # (a) f2 골든: product 파드 → INTERNAL-KSPM-PRIVILEGED-001, open
    p = f_product[0] if f_product else {}
    product_ok = (
        p.get("control_id") == "INTERNAL-KSPM-PRIVILEGED-001"
        and p.get("resource_id") == "aws:eks_pod:shop/product"
        and p.get("status") == "open"
        and "kube-bench:5.2.5" in p.get("sources", [])
    )
    checks.append(("f2 골든(product) — control_id·resource_id·status·source 일치", product_ok))

    # (b) f13 골든: member 파드 → INTERNAL-KSPM-PRIVILEGED-001, open
    m = f_member[0] if f_member else {}
    member_ok = (
        m.get("control_id") == "INTERNAL-KSPM-PRIVILEGED-001"
        and m.get("resource_id") == "aws:eks_pod:shop/member"
        and m.get("status") == "open"
        and "kube-bench:5.2.6" in m.get("sources", [])
    )
    checks.append(("f13 골든(member) — control_id·resource_id·status·source 일치", member_ok))

    # (c) pillar = "kspm" 전부
    pillar_ok = all(f["pillar"] == "kspm" for f in all_findings)
    checks.append(("pillar = kspm", pillar_ok))

    # (d) UNKNOWN control 없음
    no_unknown = not any(f["control_id"] == "INTERNAL-UNKNOWN-001" for f in all_findings)
    checks.append(("INTERNAL-UNKNOWN-001 없음", no_unknown))

    # (e) PASS → status="remediated" 전환 확인(order 파드, 골든과 무관한 추가 검증)
    o = f_order[0] if f_order else {}
    remediated_ok = o.get("status") == "remediated"
    checks.append(("PASS 결과 → status=remediated 전환(order, 회귀 방지용)", remediated_ok))

    all_ok = True
    for label, ok in checks:
        status = "OK ✅" if ok else "FAIL ⚠️"
        print(f"  {status}  {label}")
        if not ok:
            all_ok = False

    return all_ok


def main() -> int:
    _hr("워크로드 스캐너 데모 — Trivy + kube-bench → ingest-envelope → OCSF-lite finding")

    trivy_ok = _run_trivy_demo()
    kube_bench_ok = _run_kube_bench_demo()

    _hr("전체 결과")
    print("  Trivy      :", "OK ✅" if trivy_ok else "FAIL ⚠️")
    print("  kube-bench :", "OK ✅" if kube_bench_ok else "FAIL ⚠️")

    all_ok = trivy_ok and kube_bench_ok
    print("\n전체:", "OK ✅" if all_ok else "FAIL ⚠️")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
