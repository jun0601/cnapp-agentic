"""Azure Entra ID CIEM 스캐너 (진우 담당).

역할:
  Prowler Azure의 entra_* 체크 결과(과도권한 App Registration·SP 자격증명
  과다유효기간·위험한 admin consent·App 설정 미스컨피그)를 계약⑤ ingest-envelope으로
  감싸 반환한다. 이후 Normalizer(pipeline/normalize)가 envelope → 계약① finding 변환.

대상 control(계약 control-catalog.json):
  INTERNAL-ENTRA-OVERPRIV-APP-001    과도권한 App Registration (Directory.ReadWrite.All 등)
  INTERNAL-ENTRA-SP-CRED-001         SP 자격증명 과다유효기간/유출 위험
  INTERNAL-ENTRA-RISKY-CONSENT-001   미검증 앱에 위험한 admin consent
  INTERNAL-ENTRA-INSECURE-CFG-001    App Registration 설정 미스컨피그(Defender secure-score 축)

⚠️ 실측 정정(2026-07-08): 체크 패턴이 원래 가정한 `entra_id_*`가 아니라 **`entra_*`**다
(Prowler v5 기준, 언더스코어 `id` 없음 — GitHub `prowler-cloud/prowler` 소스로 실측 확인).
control-catalog.json의 sources를 실제 체크명으로 정정함. 단 OVERPRIV-APP과 동등한 체크는
azure provider의 entra 서비스엔 없고 **m365 provider에만** 존재(entra_app_registration_
no_unused_privileged_permissions) — 이 클래스는 여전히 provider="azure"만 호출하므로
OVERPRIV-APP은 현재 코드 경로로 실 데이터에 도달 못함(golden mock 전용 유지).
INSECURE-CFG(redirect URI 미스컨피그)는 azure·m365 어느 쪽에도 대응 체크가 없어 실 소스 없음.
provider=m365로 확장은 별도 과제(CI 키리스 인증 문제 — m365 --az-cli-auth는 Prowler 자체
코드 주석에 미작동 명시, --sp-env-auth는 기본적으로 client secret을 요구해 D4 키리스 원칙과
충돌 소지, 워크로드ID 페더레이션 env var 조합으로 우회 가능할 수 있으나 미검증).

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

    def scan_prowler(self, checks: str = "entra_*", timeout: int = 600) -> List[dict]:
        """prowler CLI(Azure)로 entra_* 체크만 실행 → prowler-json 봉투[] 반환.

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
