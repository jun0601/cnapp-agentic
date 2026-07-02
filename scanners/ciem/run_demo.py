"""Azure Entra CIEM 스캐너 데모 — Prowler entra_id_* 체크 → ingest-envelope → OCSF-lite finding.

실행: 레포 루트에서  python -m scanners.ciem.run_demo

무슨 일이 일어나는가:
  1. mock Prowler Azure 체크 결과 4건 (골든 f8·f9·f16·f17과 동일 리소스·checkID)을 준비
  2. EntraCIEMScanner.scan_from_json() 으로 체크 1건당 계약⑤ ingest-envelope 조립
  3. Normalizer.normalize(envelope) 으로 계약① finding 변환
  4. 골든 정합 검증:
     - 4개 checkID가 각각 올바른 INTERNAL-ENTRA-* control_id로 매핑되는가
     - resource_id가 mock-findings.json 골든 f8·f9·f16·f17과 캐논 일치하는가
     - severity_id 변환이 올바른가 (critical→1, high→2, low→4)
     - pillar가 올바른가 (overpriv/sp-cred/consent=ciem, insecure-cfg=cspm)
     - INTERNAL-UNKNOWN-001 없는가

실배포 스왑:
  EntraCIEMScanner().scan_prowler() — Prowler SP(GitHub OIDC 키리스)로 인증된 환경에서
  실 Azure 테넌트를 스캔. 봉투화·정규화 로직은 무변.
"""
from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from pipeline.normalize.normalizer import Normalizer
from scanners.ciem.entra import EntraCIEMScanner

# ── mock Prowler Azure 체크 결과 (실 prowler azure 출력과 동일 필드 구조) ──
# resourceId는 캐논 형식(azure:type:native_id) 그대로 전달 — Prowler Azure는 AWS ARN이
# 없어 스캐너 단계에서 canonical passthrough로 준다(4.4.1a). 골든 f8·f9·f16·f17과 일치.
MOCK_PROWLER_AZURE_CHECKS = [
    # ── f8 골든 finding: 과도권한 App Registration ─────────────────────
    {
        "checkID": "entra_id_app_registration_overprivileged",
        "checkTitle": "Entra App Registration granted Directory.ReadWrite.All (over-privileged)",
        "status": "FAIL",
        "severity": "critical",
        "service": "appregistration",
        "resourceId": "azure:app_registration:a1b2c3d4-1111-2222-3333-444455556666",
        "timestamp": "2026-07-02T01:20:00Z",
        "cloud": "azure",
    },
    # ── f9 골든 finding: 미검증 앱에 위험한 admin consent (같은 앱 등록) ──
    {
        "checkID": "entra_id_admin_consent_unverified_app",
        "checkTitle": "Risky admin consent (User.ReadWrite.All) granted to unverified app",
        "status": "FAIL",
        "severity": "high",
        "service": "appregistration",
        "resourceId": "azure:app_registration:a1b2c3d4-1111-2222-3333-444455556666",
        "timestamp": "2026-07-02T01:20:00Z",
        "cloud": "azure",
    },
    # ── f16 골든 finding: SP 자격증명 무만료 ────────────────────────────
    {
        "checkID": "entra_id_sp_credential_no_expiry",
        "checkTitle": "Service Principal credential without expiry (leak risk)",
        "status": "FAIL",
        "severity": "high",
        "service": "entraid",
        "resourceId": "azure:service_principal:b2c3d4e5-7777-8888-9999-aaaabbbbcccc",
        "timestamp": "2026-07-02T01:20:00Z",
        "cloud": "azure",
    },
    # ── f17 골든 finding: App Registration 설정 미스컨피그(cspm 축) ─────
    {
        "checkID": "entra_id_app_redirect_uri_insecure",
        "checkTitle": "Defender for Cloud secure score: insecure default on app registration",
        "status": "FAIL",
        "severity": "low",
        "service": "appregistration",
        "resourceId": "azure:app_registration:c3d4e5f6-2222-3333-4444-555566667777",
        "timestamp": "2026-07-02T01:20:00Z",
        "cloud": "azure",
    },
]

# checkID → 기대 골든 값 (control_id, resource_id, severity_id, pillar, resource_type)
_EXPECTED = {
    "entra_id_app_registration_overprivileged": (
        "INTERNAL-ENTRA-OVERPRIV-APP-001",
        "azure:app_registration:a1b2c3d4-1111-2222-3333-444455556666",
        1, "ciem", "app_registration",
    ),
    "entra_id_admin_consent_unverified_app": (
        "INTERNAL-ENTRA-RISKY-CONSENT-001",
        "azure:app_registration:a1b2c3d4-1111-2222-3333-444455556666",
        2, "ciem", "app_registration",
    ),
    "entra_id_sp_credential_no_expiry": (
        "INTERNAL-ENTRA-SP-CRED-001",
        "azure:service_principal:b2c3d4e5-7777-8888-9999-aaaabbbbcccc",
        2, "ciem", "service_principal",
    ),
    "entra_id_app_redirect_uri_insecure": (
        "INTERNAL-ENTRA-INSECURE-CFG-001",
        "azure:app_registration:c3d4e5f6-2222-3333-4444-555566667777",
        4, "cspm", "app_registration",
    ),
}


def _hr(title: str) -> None:
    print("\n" + "=" * 64 + "\n" + title + "\n" + "=" * 64)


def main() -> int:
    scanner = EntraCIEMScanner()
    normalizer = Normalizer()

    _hr("Azure Entra CIEM 스캐너 데모 — Prowler entra_id_* → ingest-envelope → OCSF-lite finding")

    findings = []

    # ── 1·2단계: 체크 1건당 envelope 조립 → finding 변환 ─────────────
    print("\n[1~2단계] EntraCIEMScanner.scan_from_json() → Normalizer.normalize() (체크 4건)")
    for check in MOCK_PROWLER_AZURE_CHECKS:
        envelope = scanner.scan_from_json(check)
        parsed = normalizer.normalize(envelope)
        findings.extend(parsed)

    print(f"  finding {len(findings)}건 생성\n")

    sev_label = {1: "CRITICAL", 2: "HIGH", 3: "MEDIUM", 4: "LOW", 5: "INFO"}
    for f in findings:
        print(f"  - [{sev_label.get(f['severity_id'], '?')}] {f['control_id']}")
        print(f"    checkID    : {f['sources'][0].replace('prowler:', '')}")
        print(f"    resource   : {f['resource_id']} ({f['resource_type']})")
        print(f"    pillar     : {f['pillar']}")
        print(f"    dedup_key  : {f['dedup_key']}")
        print()

    # ── 3단계: 골든 정합 검증 ─────────────────────────────────────────
    _hr("골든 정합 검증")

    checks_result = []

    # (a) 체크 4건 → finding 4건 (같은 app registration이라도 control_id 달라 dedup 안 됨)
    checks_result.append(("finding 4건 생성(dedup 없음)", len(findings) == 4))

    # (b) checkID별 control_id·resource_id·severity_id·pillar·resource_type 전부 golden 일치
    by_check = {f["sources"][0].replace("prowler:", ""): f for f in findings}
    all_match = True
    for check_id, (ctrl, rid, sev, pillar, rtype) in _EXPECTED.items():
        f = by_check.get(check_id)
        ok = bool(
            f
            and f["control_id"] == ctrl
            and f["resource_id"] == rid
            and f["severity_id"] == sev
            and f["pillar"] == pillar
            and f["resource_type"] == rtype
        )
        if not ok:
            all_match = False
        checks_result.append((f"{check_id} → {ctrl} (golden 일치)", ok))

    # (c) UNKNOWN control 없음
    no_unknown = not any(f["control_id"] == "INTERNAL-UNKNOWN-001" for f in findings)
    checks_result.append(("INTERNAL-UNKNOWN-001 없음", no_unknown))

    all_ok = True
    for label, ok in checks_result:
        status = "OK ✅" if ok else "FAIL ⚠️"
        print(f"  {status}  {label}")
        if not ok:
            all_ok = False

    print("\n전체:", "OK ✅" if all_ok else "FAIL ⚠️")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
