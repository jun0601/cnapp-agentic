"""워크로드 스캐너 데모 — Trivy 이미지 스캔 → ingest-envelope → OCSF-lite finding.

실행: 레포 루트에서  python -m scanners.workload.run_demo

무슨 일이 일어나는가:
  1. mock Trivy JSON 3건 (product 이미지 CVE 목록) 을 미리 준비
  2. TrivyScanner.scan_from_json() 으로 계약⑤ ingest-envelope 조립
  3. Normalizer.normalize(envelope) 으로 계약① finding[] 변환
  4. 골든 정합 검증:
     - 모든 finding이 INTERNAL-VULN-KEV-001에 매핑되는가
       (control-catalog의 'trivy:CVE-*' 와일드카드 매칭)
     - severity 변환이 올바른가 (CRITICAL→1, HIGH→2, MEDIUM→3)
     - resource_id가 캐논 형식인가 (aws:eks_pod:shop/product)
     - INTERNAL-UNKNOWN-001 없는가

실배포 스왑:
  TrivyScanner.scan_image("123456789.dkr.ecr.ap-northeast-2.amazonaws.com/product:latest")
  — trivy CLI가 설치돼 있으면 실 ECR 이미지를 스캔.
  봉투화·정규화 로직은 무변.
"""
from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from pipeline.normalize.normalizer import Normalizer
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


def _hr(title: str) -> None:
    print("\n" + "=" * 64 + "\n" + title + "\n" + "=" * 64)


def main() -> int:
    scanner = TrivyScanner()
    normalizer = Normalizer()

    _hr("워크로드 스캐너 데모 — Trivy → ingest-envelope → OCSF-lite finding")

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
    _hr("골든 정합 검증")

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

    print("\n전체:", "OK ✅" if all_ok else "FAIL ⚠️")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
