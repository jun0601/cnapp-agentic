"""정규화부 데모 — 실 스캐너가 내놓을 법한 raw JSON → OCSF-lite finding 변환 확인.

실행: 레포 루트에서  python -m pipeline.normalize.run_demo

각 스캐너 포맷(ASFF·prowler-json·trivy-json)으로 mock envelope을 만들어
골든 시나리오 finding들이 올바르게 변환되는지 검증한다.

실배포 스왑: Lambda 핸들러가 SQS에서 꺼낸 실제 envelope을 Normalizer().normalize()에 넘기면 됨.
"""
from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from pipeline.normalize.normalizer import Normalizer

# ── mock envelope 목록 ────────────────────────────────────────────────
# 실 스캐너가 내놓는 포맷을 그대로 흉내. 골든 시나리오 핵심 finding 위주.

MOCK_ENVELOPES = [
    # ── Security Hub ASFF: S3 공개 버킷 (f6 → INTERNAL-S3-PUBLIC-001) ──
    {
        "envelope_id": "e0000001-0000-4000-8000-000000000001",
        "source": "securityhub",
        "source_format": "asff",
        "cloud_hint": "aws",
        "scan_batch_id": "batch-2026-07-02-securityhub",
        "ingested_at": "2026-07-02T01:00:00Z",
        "raw_inline": {
            "SchemaVersion": "2018-10-08",
            "Title": "S3 general purpose buckets should block public access",
            "Severity": {"Label": "HIGH"},
            "Resources": [{"Type": "AwsS3Bucket", "Id": "arn:aws:s3:::member-pii-prod"}],
            "Compliance": {"Status": "FAILED"},
            "ProductFields": {"ControlId": "S3.8"},
            "UpdatedAt": "2026-07-02T01:00:00Z",
            "CreatedAt": "2026-07-01T00:00:00Z",
        },
    },
    # ── Macie ASFF: PII 탐지 (f7 → INTERNAL-DATA-PII-EXPOSED-001) ──
    {
        "envelope_id": "e0000001-0000-4000-8000-000000000002",
        "source": "macie",
        "source_format": "asff",
        "cloud_hint": "aws",
        "scan_batch_id": "batch-2026-07-02-macie",
        "ingested_at": "2026-07-02T01:05:00Z",
        "raw_inline": {
            "SchemaVersion": "2018-10-08",
            "Title": "SensitiveData: member-pii-prod contains PII",
            "Severity": {"Label": "HIGH"},
            "Types": ["Sensitive Data Identifications/PII/SensitiveData:S3Object"],
            "Resources": [{"Type": "AwsS3Bucket", "Id": "arn:aws:s3:::member-pii-prod"}],
            "Compliance": {"Status": "FAILED"},
            "UpdatedAt": "2026-07-02T01:05:00Z",
            "CreatedAt": "2026-07-01T00:00:00Z",
        },
    },
    # ── Security Hub ASFF: SG 0.0.0.0/0 (f3 → INTERNAL-SG-OPEN-INGRESS-001) ──
    {
        "envelope_id": "e0000001-0000-4000-8000-000000000003",
        "source": "securityhub",
        "source_format": "asff",
        "cloud_hint": "aws",
        "scan_batch_id": "batch-2026-07-02-securityhub",
        "ingested_at": "2026-07-02T01:00:00Z",
        "raw_inline": {
            "SchemaVersion": "2018-10-08",
            "Title": "Security groups should not allow unrestricted access to ports with high risk",
            "Severity": {"Label": "HIGH"},
            "Resources": [{"Type": "AwsEc2SecurityGroup", "Id": "arn:aws:ec2:ap-northeast-2:123456789012:security-group/sg-0product1234"}],
            "Compliance": {"Status": "FAILED"},
            "ProductFields": {"ControlId": "EC2.19"},
            "UpdatedAt": "2026-07-02T01:00:00Z",
            "CreatedAt": "2026-07-01T00:00:00Z",
        },
    },
    # ── Trivy JSON: KEV CVE (f1 → INTERNAL-VULN-KEV-001) ──
    {
        "envelope_id": "e0000001-0000-4000-8000-000000000004",
        "source": "trivy",
        "source_format": "trivy-json",
        "cloud_hint": "aws",
        "scan_batch_id": "batch-2026-07-02-trivy",
        "ingested_at": "2026-07-02T01:10:00Z",
        "raw_inline": {
            "SchemaVersion": 2,
            "ArtifactName": "shop/product",
            "ArtifactType": "container_image",
            "Results": [{
                "Target": "shop/product:latest",
                "Vulnerabilities": [
                    {"VulnerabilityID": "CVE-2024-38856", "PkgName": "openssl", "Severity": "CRITICAL"},
                ],
            }],
        },
    },
    # ── Prowler JSON 배치: IAM 과도권한(f4) + 평문 시크릿(f5) ──
    {
        "envelope_id": "e0000001-0000-4000-8000-000000000005",
        "source": "prowler-aws",
        "source_format": "prowler-json",
        "cloud_hint": "aws",
        "scan_batch_id": "batch-2026-07-02-prowler-aws",
        "ingested_at": "2026-07-02T01:15:00Z",
        "raw_inline": [
            {
                "checkID": "iam_inline_policy_allows_privilege_escalation",
                "checkTitle": "IAM role has over-privileged inline policy (s3:*)",
                "status": "FAIL",
                "severity": "critical",
                "service": "iam",
                "resourceArn": "arn:aws:iam::123456789012:role/order-irsa",
                "timestamp": "2026-07-02T01:15:00Z",
                "cloud": "aws",
            },
            {
                "checkID": "eks_cluster_secret_encryption",
                "checkTitle": "Plaintext Azure SP credential in pod env (order)",
                "status": "FAIL",
                "severity": "critical",
                "service": "secretsmanager",
                "resourceId": "shop/order/AZURE_SP_CRED",
                "timestamp": "2026-07-02T01:15:00Z",
                "cloud": "aws",
            },
        ],
    },
    # ── Prowler Azure JSON: Entra 과도권한 App (f8 → INTERNAL-ENTRA-OVERPRIV-APP-001) ──
    {
        "envelope_id": "e0000001-0000-4000-8000-000000000006",
        "source": "prowler-azure",
        "source_format": "prowler-json",
        "cloud_hint": "azure",
        "scan_batch_id": "batch-2026-07-02-prowler-azure",
        "ingested_at": "2026-07-02T01:20:00Z",
        "raw_inline": {
            "checkID": "entra_app_registration_no_unused_privileged_permissions",
            "checkTitle": "Entra App Registration granted Directory.ReadWrite.All",
            "status": "FAIL",
            "severity": "critical",
            "service": "appregistration",
            "resourceId": "azure:app_registration:283ca885-134e-4a74-92d6-7dd1ed9cd46f",
            "timestamp": "2026-07-02T01:20:00Z",
            "cloud": "azure",
        },
    },
    # ── Prowler Azure JSON: SP 장기 유효 시크릿 (f16 → INTERNAL-ENTRA-SP-CRED-001) ──
    {
        "envelope_id": "e0000001-0000-4000-8000-000000000007",
        "source": "prowler-azure",
        "source_format": "prowler-json",
        "cloud_hint": "azure",
        "scan_batch_id": "batch-2026-07-02-prowler-azure",
        "ingested_at": "2026-07-02T01:20:00Z",
        "raw_inline": {
            "checkID": "entra_app_registration_credential_not_expired",
            "checkTitle": "Service Principal credential with excessive validity (24 months)",
            "status": "FAIL",
            "severity": "high",
            "service": "entraid",
            "resourceId": "azure:service_principal:b2c3d4e5-7777-8888-9999-aaaabbbbcccc",
            "timestamp": "2026-07-02T01:20:00Z",
            "cloud": "azure",
        },
    },
    # ── dedup 테스트: Prowler도 같은 S3 공개버킷 탐지 → Security Hub와 머지 ──
    {
        "envelope_id": "e0000001-0000-4000-8000-000000000008",
        "source": "prowler-aws",
        "source_format": "prowler-json",
        "cloud_hint": "aws",
        "scan_batch_id": "batch-2026-07-02-prowler-aws",
        "ingested_at": "2026-07-02T01:15:00Z",
        "raw_inline": {
            "checkID": "s3_bucket_public_access",
            "checkTitle": "S3 Bucket Public Access Block disabled",
            "status": "FAIL",
            "severity": "high",
            "service": "s3",
            "resourceArn": "arn:aws:s3:::member-pii-prod",
            "timestamp": "2026-07-02T01:15:00Z",
            "cloud": "aws",
        },
    },
    # ── OCSF(실 Prowler json-ocsf 경로) AWS: S3 공개버킷 → INTERNAL-S3-PUBLIC-001 ──
    #    설계 확정(§24·계약⑤): 실 Prowler는 OCSF 출력 → ingest가 source_format="ocsf" 봉투화.
    #    OCSF 파서 하나로 AWS·Azure 둘 다 커버함을 아래 2건(AWS/Azure)으로 증명.
    {
        "envelope_id": "e0000001-0000-4000-8000-000000000009",
        "source": "prowler-aws",
        "source_format": "ocsf",
        "cloud_hint": "aws",
        "scan_batch_id": "batch-2026-07-02-prowler-ocsf-aws",
        "ingested_at": "2026-07-02T01:25:00Z",
        "raw_inline": {
            "metadata": {"event_code": "s3_bucket_public_access",
                         "product": {"name": "Prowler"}},
            "severity": "High",
            "status_code": "FAIL",
            "finding_info": {"title": "S3 Bucket Public Access Block disabled"},
            "cloud": {"provider": "aws"},
            "resources": [{"uid": "arn:aws:s3:::member-pii-prod",
                           "group": {"name": "s3"}}],
            "time_dt": "2026-07-02T01:25:00Z",
        },
    },
    # ── OCSF(실 Prowler json-ocsf 경로) Azure: Entra 과도권한 App → INTERNAL-ENTRA-OVERPRIV-APP-001 ──
    {
        "envelope_id": "e0000001-0000-4000-8000-00000000000a",
        "source": "prowler-azure",
        "source_format": "ocsf",
        "cloud_hint": "azure",
        "scan_batch_id": "batch-2026-07-02-prowler-ocsf-azure",
        "ingested_at": "2026-07-02T01:25:00Z",
        "raw_inline": {
            "metadata": {"event_code": "entra_app_registration_no_unused_privileged_permissions",
                         "product": {"name": "Prowler"}},
            "severity": "Critical",
            "status_code": "FAIL",
            "finding_info": {"title": "Entra App Registration granted Directory.ReadWrite.All"},
            "cloud": {"provider": "azure"},
            "resources": [{"uid": "azure:app_registration:283ca885-134e-4a74-92d6-7dd1ed9cd46f",
                           "group": {"name": "appregistration"}}],
            "time_dt": "2026-07-02T01:25:00Z",
        },
    },
]


def _hr(title: str) -> None:
    print("\n" + "=" * 64 + "\n" + title + "\n" + "=" * 64)


def main() -> int:
    normalizer = Normalizer()
    all_findings: list = []

    _hr("정규화부 데모 — mock 스캐너 raw → OCSF-lite finding")

    for env in MOCK_ENVELOPES:
        findings = normalizer.normalize(env)
        all_findings.extend(findings)
        src = env["source"]
        fmt = env["source_format"]
        print(f"\n[{src} / {fmt}]  → finding {len(findings)}건")
        for f in findings:
            print(f"  ✓ [{f['severity_id']}] {f['control_id']}")
            print(f"    resource : {f['resource_id']}")
            print(f"    pillar   : {f['pillar']}")
            print(f"    sources  : {f['sources']}")
            print(f"    dedup_key: {f['dedup_key']}")

    # ── 전체 dedup (여러 봉투에서 같은 finding이 나올 수 있음) ──────
    from pipeline.normalize.normalizer import dedup_findings
    deduped = dedup_findings(all_findings)

    _hr("전체 dedup 결과")
    print(f"원본 합계 {len(all_findings)}건  →  dedup 후 {len(deduped)}건")
    print("\n[dedup 효과 — sources 머지된 finding]")
    for f in deduped:
        if len(f["sources"]) > 1:
            print(f"  {f['resource_id']} | {f['control_id']}")
            print(f"  sources: {f['sources']}")

    # ── OCSF 파서 단독 검증 (dedup 머지로 가려지는 silent-fail 방지) ──
    _hr("OCSF 파서 단독 검증 (Prowler json-ocsf — AWS+Azure 파서 1개)")
    ocsf_envs = [e for e in MOCK_ENVELOPES if e["source_format"] == "ocsf"]
    ocsf_findings: list = []
    for e in ocsf_envs:
        ocsf_findings.extend(normalizer.normalize(e))
    ocsf_ctrls = {f["control_id"] for f in ocsf_findings}
    ocsf_ok = (
        len(ocsf_findings) == len(ocsf_envs)                       # 봉투마다 finding 1건
        and "INTERNAL-S3-PUBLIC-001" in ocsf_ctrls                 # AWS OCSF
        and "INTERNAL-ENTRA-OVERPRIV-APP-001" in ocsf_ctrls        # Azure OCSF (동일 파서)
        and "INTERNAL-UNKNOWN-001" not in ocsf_ctrls               # check_id 매핑 성공
    )
    for f in ocsf_findings:
        print(f"  ✓ {f['cloud']:5s} {f['control_id']} ({f['resource_id']})")
    print("OCSF 파서 AWS+Azure 매핑: %s" % ("OK ✅" if ocsf_ok else "FAIL ⚠️"))

    # ── 골든 정합 검증 ──────────────────────────────────────────────
    _hr("골든 정합 검증")
    ctrl_ids = {f["control_id"] for f in deduped}
    golden_expected = {
        "INTERNAL-S3-PUBLIC-001",
        "INTERNAL-DATA-PII-EXPOSED-001",
        "INTERNAL-SG-OPEN-INGRESS-001",
        "INTERNAL-VULN-KEV-001",
        "INTERNAL-IAM-OVERPRIV-001",
        "INTERNAL-ENTRA-OVERPRIV-APP-001",
        "INTERNAL-ENTRA-SP-CRED-001",
    }
    missing = golden_expected - ctrl_ids
    extra_unknown = {c for c in ctrl_ids if c == "INTERNAL-UNKNOWN-001"}

    ok = not missing and not extra_unknown and ocsf_ok
    print("골든 control_id 전부 매핑: %s" % ("OK ✅" if not missing else "FAIL ⚠️  누락: " + str(missing)))
    print("UNKNOWN control 없음    : %s" % ("OK ✅" if not extra_unknown else "FAIL ⚠️  있음"))
    print("OCSF 파서(AWS+Azure)     : %s" % ("OK ✅" if ocsf_ok else "FAIL ⚠️"))
    print("전체: %s" % ("OK ✅" if ok else "FAIL ⚠️"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
