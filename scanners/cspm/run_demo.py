"""CSPM 스캐너 데모 — 실 스캐너가 내놓을 원본 → 계약⑤ 봉투 → OCSF-lite finding.

실행: 레포 루트에서  python -m scanners.cspm.run_demo

흐름(진우 workload 데모와 동형):
  1. Security Hub·Macie(ASFF) / Prowler(prowler-json) 원본을 미리 준비(실 스캐너 출력 구조)
  2. CSPMScanner.scan_from_json() 으로 계약⑤ ingest-envelope 조립
  3. Normalizer.normalize(envelope) 으로 계약① finding[] 변환(정규화부=진우)
  4. 골든 정합 검증: 준형 CSPM/CIEM 소스가 내는 골든 finding 5종이 다 매핑되는가

준형 CSPM/CIEM 골든 findings(=golden attack-path의 AWS 설정·데이터·권한 노드 소스):
  INTERNAL-S3-PUBLIC-001(f6) · INTERNAL-SG-OPEN-INGRESS-001(f3) ·
  INTERNAL-DATA-PII-EXPOSED-001(f7) · INTERNAL-IAM-OVERPRIV-001(f4) ·
  INTERNAL-SECRET-PLAINTEXT-001(f5)
(취약점·KSPM=진우 workload / Entra=진우 ciem 이라 여기 없음 — 도메인 분리)

실배포 스왑: scan_from_json → scan_securityhub()(boto3) / scan_prowler()(CLI). 봉투화·정규화 무변.
"""
from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from pipeline.normalize.normalizer import Normalizer, dedup_findings
from scanners.cspm.cspm import CSPMScanner

# ── 실 스캐너 출력 구조와 동일한 원본(단건) — (raw, source, source_format) ──
# ASFF = Security Hub·Macie / prowler-json = Prowler(AWS). 정규화부가 둘 다 파싱.
_CSPM_RAWS = [
    # Security Hub ASFF — S3 공개 버킷(f6 → INTERNAL-S3-PUBLIC-001)
    ({
        "SchemaVersion": "2018-10-08",
        "Title": "S3 general purpose buckets should block public access",
        "Severity": {"Label": "HIGH"},
        "Resources": [{"Type": "AwsS3Bucket", "Id": "arn:aws:s3:::member-pii-prod"}],
        "Compliance": {"Status": "FAILED"},
        "ProductFields": {"ControlId": "S3.8"},
        "UpdatedAt": "2026-07-02T01:00:00Z", "CreatedAt": "2026-07-01T00:00:00Z",
    }, "securityhub", "asff"),
    # Security Hub ASFF — SG 0.0.0.0/0(f3 → INTERNAL-SG-OPEN-INGRESS-001)
    ({
        "SchemaVersion": "2018-10-08",
        "Title": "Security groups should not allow unrestricted access to high-risk ports",
        "Severity": {"Label": "HIGH"},
        "Resources": [{"Type": "AwsEc2SecurityGroup",
                       "Id": "arn:aws:ec2:ap-northeast-2:123456789012:security-group/sg-0product1234"}],
        "Compliance": {"Status": "FAILED"},
        "ProductFields": {"ControlId": "EC2.19"},
        "UpdatedAt": "2026-07-02T01:00:00Z", "CreatedAt": "2026-07-01T00:00:00Z",
    }, "securityhub", "asff"),
    # Macie ASFF — PII 탐지(f7 → INTERNAL-DATA-PII-EXPOSED-001)
    ({
        "SchemaVersion": "2018-10-08",
        "Title": "SensitiveData: member-pii-prod contains PII",
        "Severity": {"Label": "HIGH"},
        "Types": ["Sensitive Data Identifications/PII/SensitiveData:S3Object"],
        "Resources": [{"Type": "AwsS3Bucket", "Id": "arn:aws:s3:::member-pii-prod"}],
        "Compliance": {"Status": "FAILED"},
        "UpdatedAt": "2026-07-02T01:05:00Z", "CreatedAt": "2026-07-01T00:00:00Z",
    }, "macie", "asff"),
    # Prowler(AWS) prowler-json — 과도 IRSA(f4 → INTERNAL-IAM-OVERPRIV-001)
    ({
        "checkID": "iam_inline_policy_allows_privilege_escalation",
        "checkTitle": "IAM role has over-privileged inline policy (s3:*)",
        "status": "FAIL", "severity": "critical", "service": "iam",
        "resourceArn": "arn:aws:iam::123456789012:role/order-irsa",
        "timestamp": "2026-07-02T01:15:00Z", "cloud": "aws",
    }, "prowler-aws", "prowler-json"),
    # Prowler(AWS) prowler-json — 평문 Azure SP 시크릿(f5 → INTERNAL-SECRET-PLAINTEXT-001)
    ({
        "checkID": "eks_cluster_secret_encryption",
        "checkTitle": "Plaintext Azure SP credential in pod env (order)",
        "status": "FAIL", "severity": "critical", "service": "secretsmanager",
        "resourceId": "aws:secret_plaintext:shop/order/AZURE_SP_CRED",
        "timestamp": "2026-07-02T01:15:00Z", "cloud": "aws",
    }, "prowler-aws", "prowler-json"),
    # Prowler(AWS)도 같은 공개 S3 탐지 → Security Hub와 dedup(sources 머지) 시연
    ({
        "checkID": "s3_bucket_public_access",
        "checkTitle": "S3 Bucket Public Access Block disabled",
        "status": "FAIL", "severity": "high", "service": "s3",
        "resourceArn": "arn:aws:s3:::member-pii-prod",
        "timestamp": "2026-07-02T01:15:00Z", "cloud": "aws",
    }, "prowler-aws", "prowler-json"),
]

_GOLDEN_CSPM = {
    "INTERNAL-S3-PUBLIC-001",
    "INTERNAL-SG-OPEN-INGRESS-001",
    "INTERNAL-DATA-PII-EXPOSED-001",
    "INTERNAL-IAM-OVERPRIV-001",
    "INTERNAL-SECRET-PLAINTEXT-001",
}


def _hr(t: str) -> None:
    print("\n" + "=" * 64 + "\n" + t + "\n" + "=" * 64)


def main() -> int:
    scanner = CSPMScanner()
    normalizer = Normalizer()

    _hr("CSPM 스캐너 데모 — SecurityHub·Macie·Prowler → 계약⑤ 봉투 → OCSF-lite finding")

    all_findings: list = []
    for raw, source, fmt in _CSPM_RAWS:
        env = scanner.scan_from_json(raw, source, fmt)
        findings = normalizer.normalize(env)
        all_findings.extend(findings)
        print("\n[%s / %s]  → finding %d건" % (source, fmt, len(findings)))
        for f in findings:
            print("  ✓ [%d] %s / %s" % (f["severity_id"], f["control_id"], f["resource_id"]))
            print("      pillar=%s  sources=%s" % (f["pillar"], f["sources"]))

    deduped = dedup_findings(all_findings)
    _hr("dedup (SecurityHub + Prowler 같은 공개 S3 → 머지)")
    print("원본 %d건 → dedup 후 %d건" % (len(all_findings), len(deduped)))
    for f in deduped:
        if len(f["sources"]) > 1:
            print("  머지: %s | %s  sources=%s" % (f["resource_id"], f["control_id"], f["sources"]))

    _hr("골든 정합 검증 (준형 CSPM/CIEM 소스 5종)")
    ctrl_ids = {f["control_id"] for f in deduped}
    missing = _GOLDEN_CSPM - ctrl_ids
    no_unknown = "INTERNAL-UNKNOWN-001" not in ctrl_ids
    pillar_ok = all(f["pillar"] in {"cspm", "ciem", "data"} for f in deduped)

    print("골든 CSPM control 5종 전부 매핑: %s"
          % ("OK ✅" if not missing else "FAIL ⚠️ 누락: " + str(missing)))
    print("UNKNOWN control 없음           : %s" % ("OK ✅" if no_unknown else "FAIL ⚠️"))
    print("pillar ∈ {cspm,ciem,data}      : %s" % ("OK ✅" if pillar_ok else "FAIL ⚠️"))
    ok = not missing and no_unknown and pillar_ok
    print("\n전체: %s" % ("OK ✅" if ok else "FAIL ⚠️"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
