"""Azure Entra ID CIEM 스캐너 (진우 담당).

역할:
  Prowler Azure의 entra_id_* 체크 결과(과도권한 App Registration·SP 자격증명
  무만료·위험한 admin consent·App 설정 미스컨피그)를 계약⑤ ingest-envelope으로
  감싸 반환한다. 이후 Normalizer(pipeline/normalize)가 envelope → 계약① finding 변환.

대상 control(계약 control-catalog.json):
  INTERNAL-ENTRA-OVERPRIV-APP-001    과도권한 App Registration (Directory.ReadWrite.All 등)
  INTERNAL-ENTRA-SP-CRED-001         SP 자격증명 무만료/유출 위험
  INTERNAL-ENTRA-RISKY-CONSENT-001   미검증 앱에 위험한 admin consent
  INTERNAL-ENTRA-INSECURE-CFG-001    App Registration 설정 미스컨피그(Defender secure-score 축)

실배포 스왑:
  Prowler SP(manual-infra §3.6.3, GitHub OIDC 키리스) → scan_prowler() →
  envelope[]을 SQS(ingest 큐)로 publish. 이 파일의 봉투화 로직은 무변.

목업용:
  scan_from_json(raw) — Prowler CLI 없이 체크 결과 dict 직접 주입(체크 1건 = 봉투 1개).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List


class EntraCIEMScanError(Exception):
    """Entra CIEM 스캐너 실행 실패."""


class EntraCIEMScanner:
    """Prowler Azure entra_id_* 체크 결과 → 계약⑤ ingest-envelope 래퍼.

    mock: scan_from_json()으로 미리 받아둔 Prowler Azure 체크 결과를 봉투화.
    real: scan_prowler()가 CSPMScanner(provider="azure")에 위임
          (prowler CLI 실행 로직은 scanners/cspm/cspm.py와 중복 없이 재사용).
    """

    def __init__(self, prowler_bin: str = "prowler") -> None:
        self._prowler_bin = prowler_bin

    # ── 목업용 ────────────────────────────────────────────────────────

    def scan_from_json(self, raw: dict) -> dict:
        """미리 받아둔 Prowler Azure 체크 결과(단건) → 계약⑤ ingest-envelope.

        raw는 Prowler 네이티브 필드(checkID·checkTitle·status·severity·service·
        resourceId 등)를 그대로 담은 dict. Normalizer._parse_prowler가 이 필드를 읽는다.
        """
        return self._build_envelope(raw)

    # ── 실 경로 (CSPMScanner에 위임 — subprocess 로직 중복 방지) ─────────

    def scan_prowler(self, checks: str = "entra_id_*", timeout: int = 600) -> List[dict]:
        """prowler CLI(Azure)로 entra_id_* 체크만 실행 → prowler-json 봉투[] 반환.

        전제: Prowler SP(manual-infra §3.6.3, GitHub Federated Credential 키리스)로
        인증된 환경. AWS CSPM과 동일한 CLI 실행 경로를 재사용한다
        (scanners/cspm/cspm.py CSPMScanner.scan_prowler — Trivy.scan_image과 동형).
        """
        from scanners.cspm.cspm import CSPMScanner
        return CSPMScanner(prowler_bin=self._prowler_bin).scan_prowler(
            provider="azure", checks=checks, timeout=timeout
        )

    # ── 봉투화 ────────────────────────────────────────────────────────

    def _build_envelope(self, raw: dict) -> dict:
        """계약⑤ ingest-envelope 조립.

        source="prowler-azure", source_format="prowler-json", cloud_hint="azure" 고정.
        """
        return {
            "envelope_id": str(uuid.uuid4()),
            "source": "prowler-azure",
            "source_format": "prowler-json",
            "cloud_hint": "azure",
            "scan_batch_id": "prowler-azure-entra-%s" % _now_batch(),
            "ingested_at": _now(),
            "raw_inline": raw,
        }


# ── 헬퍼 ──────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _now_batch() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


# ── CLI 간이 사용 (python -m scanners.ciem.entra) ──────────────────────

def _cli_main() -> int:
    import json
    import sys
    from scanners.cspm.cspm import CSPMScanError

    scanner = EntraCIEMScanner()
    try:
        envelopes = scanner.scan_prowler()
    except CSPMScanError as e:
        print("오류:", e, file=sys.stderr)
        return 1

    print(json.dumps(envelopes, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
