"""CSPM/CIEM 스캐너 (준형 담당) — AWS 설정·데이터·권한 신호 → 계약⑤ ingest-envelope.

진우 workload(Trivy)와 **대칭 구조**: 스캐너는 '봉투화(계약⑤)'까지만, envelope→계약① finding
변환은 정규화부(pipeline/normalize, 진우) 몫. 봉투만 맞으면 바로 파이프라인에 물린다.

소스(준형 영역):
  - Security Hub  (CSPM 점검·점수)      → ASFF
  - AWS Config    (설정 규칙)           → ASFF(securityhub 경유) / custom
  - Prowler(AWS)  (오픈소스 CSPM)       → OCSF(`-M json-ocsf`, 멀티클라우드 중립 파서 재사용 — project-draft §24 확정)
  - Macie         (S3 민감데이터/DSPM)  → ASFF
  - IAM Access Analyzer (CIEM 과도권한) → (OCSF 매핑 또는 custom)
정규화부가 ASFF·OCSF·prowler-json(레거시/목업 네이티브 포맷)을 모두 파싱하므로, 스캐너는 원본을 이 포맷 중 하나로 봉투화한다.

mock-first (실 스캐너·계정 없이 CI/데모):
  scan_from_json(raw, source, source_format) — 미리 받아둔 원본을 계약⑤ 봉투로 감싼다(source_format은 호출자가 지정 — prowler-json 네이티브 포맷 목업 등 자유롭게 테스트 가능).
실 경로 (지연 import — 미설치/무자격 환경에서도 이 모듈 import는 안전):
  scan_securityhub()  — boto3 securityhub.get_findings() → FAILED만 → ASFF 봉투[]
  scan_prowler(...)   — prowler CLI를 `-M json-ocsf`로 실행 → **OCSF** 봉투[]  (Trivy.scan_image과 동형)
  (Config/Macie/AccessAnalyzer는 동일 패턴으로 확장 — 실배포 시 추가)

실배포 스왑: EventBridge(Security Hub Findings Imported 등) → 수집부(pipeline/ingest) → SQS,
또는 스캐너를 직접 호출(scan_securityhub/scan_prowler). 봉투화 로직은 무변.
"""
from __future__ import annotations

import subprocess
import uuid
from datetime import datetime, timezone
from typing import List, Optional

# 계약⑤ source/source_format enum(스키마와 동일하게 유지)
_SOURCES = {"securityhub", "config", "inspector", "prowler-aws", "prowler-azure",
            "trivy", "kube-bench", "macie", "synthetic"}
_FORMATS = {"asff", "ocsf", "prowler-json", "trivy-json", "custom"}


class CSPMScanError(Exception):
    """CSPM 스캐너 실행 실패(CLI 미설치·권한 등)."""


class CSPMScanner:
    """CSPM/CIEM 스캐너 래퍼 — 원본 → 계약⑤ ingest-envelope.

    mock: scan_from_json()으로 미리 받아둔 원본을 봉투화(CI/데모).
    real: scan_securityhub()/scan_prowler()로 실 계정 read-only 스캔.
    """

    def __init__(self, region: str = "ap-northeast-2", profile: Optional[str] = None,
                 prowler_bin: str = "prowler") -> None:
        self._region = region
        self._profile = profile
        self._prowler_bin = prowler_bin

    # ── 봉투화 (계약⑤) ────────────────────────────────────────────────
    def _build_envelope(self, raw: dict, source: str, source_format: str,
                        cloud_hint: str = "aws") -> dict:
        """계약⑤ ingest-envelope 조립(스키마 required 6필드 + raw_inline).

        source/source_format enum 위반은 여기서 차단(정규화부가 못 받는 봉투 방지).
        scan_batch_id=(source,배치) — remediated 판정 스코프(4.4.1c).
        """
        if source not in _SOURCES:
            raise CSPMScanError("source enum 위반(계약⑤): %s" % source)
        if source_format not in _FORMATS:
            raise CSPMScanError("source_format enum 위반(계약⑤): %s" % source_format)
        return {
            "envelope_id": str(uuid.uuid4()),
            "source": source,
            "source_format": source_format,
            "cloud_hint": cloud_hint,
            "scan_batch_id": "%s-%s" % (source, _now_batch()),
            "ingested_at": _now(),
            "raw_inline": raw,
        }

    def scan_from_json(self, raw: dict, source: str, source_format: str,
                       cloud_hint: str = "aws") -> dict:
        """미리 받아둔 원본(1건) → 계약⑤ 봉투. 실 스캐너 없이 end-to-end 검증용.

        raw_inline은 계약⑤상 object(단건) — 배치는 봉투를 여러 개 만든다(EventBridge 1이벤트=1봉투 모델).
        """
        return self._build_envelope(raw, source, source_format, cloud_hint)

    # ── 실 경로 (지연 import) ─────────────────────────────────────────
    def scan_securityhub(self, max_results: int = 100) -> List[dict]:
        """boto3로 Security Hub FAILED finding을 조회해 ASFF 봉투[] 반환.

        전제: Security Hub 활성(종량제 — 데모만 켜고 destroy, project-draft §22).
        read-only(securityhub:GetFindings). finding 1건 = 봉투 1개(계약⑤ raw_inline object).
        """
        try:
            import boto3
        except ImportError as e:  # pragma: no cover
            raise CSPMScanError("scan_securityhub는 boto3 필요 — pip install boto3") from e
        session = boto3.Session(profile_name=self._profile, region_name=self._region)
        client = session.client("securityhub")
        envelopes: List[dict] = []
        resp = client.get_findings(
            Filters={"ComplianceStatus": [{"Value": "FAILED", "Comparison": "EQUALS"}],
                     "RecordState": [{"Value": "ACTIVE", "Comparison": "EQUALS"}]},
            MaxResults=min(max_results, 100),
        )
        for asff in resp.get("Findings", []):
            envelopes.append(self._build_envelope(asff, "securityhub", "asff", "aws"))
        return envelopes

    def scan_prowler(self, provider: str = "aws", checks: Optional[str] = None,
                     timeout: int = 900) -> List[dict]:
        """prowler CLI를 `-M json-ocsf`로 실행 → OCSF 봉투[] 반환(Trivy.scan_image과 동형).

        prowler는 오픈소스라 read-only 자격증명만으로 계정 스캔 가능(Security Hub 미활성이어도 됨).
        provider: aws | azure. checks: 쉼표구분 체크 ID(선택).

        ⚠️ 2026-07-03 버그 수정: CLI는 OCSF 출력을 요청하면서(`-M json-ocsf`) 봉투의
        source_format을 "prowler-json"으로 잘못 태깅했었다 — 정규화부(pipeline/normalize)의
        디스패처가 source_format으로 파서를 고르는데, "prowler-json"은 _parse_prowler(다른
        필드 구조를 읽는 레거시/네이티브 포맷 파서)로 가서 실제 OCSF 데이터를 잘못 파싱해
        control_id가 전부 None(INTERNAL-UNKNOWN-001)이 되는 문제였다(mock 경로는 scan_from_json이
        format을 직접 지정해 우회하므로 run_demo로는 안 잡힘). scanners/ciem/entra.py의
        scan_prowler(Azure)도 이 메서드에 위임하므로 동일하게 영향받았음 — 함께 해결됨.

        ⚠️ 2026-07-06 실측 버그 수정(이 프로젝트 최초 실 CLI 실행): 이전 코드가 두 가지를
        잘못 가정하고 있었다(그동안 로컬 CLI 미설치라 한 번도 실행된 적이 없어서 안 걸림).
        ① `-q` 플래그는 현재 prowler(v5.x)에 없음 — 붙이면 즉시 `unrecognized arguments`로
        실패한다. ② `-M json-ocsf`는 **stdout이 아니라 파일**에 결과를 쓴다(기본
        `output/prowler-output-<account>-<timestamp>.ocsf.json`) — stdout엔 사람이 보는
        진행률 표만 나온다. 이제 `--output-directory`를 임시 디렉터리로 지정하고 그 안의
        최상위(`compliance/` 서브폴더 제외) `*.ocsf.json` 파일을 읽는다.
        """
        source = "prowler-aws" if provider == "aws" else "prowler-azure"
        cloud = "aws" if provider == "aws" else "azure"
        import glob
        import json
        import tempfile

        with tempfile.TemporaryDirectory(prefix="prowler-out-") as out_dir:
            cmd = [self._prowler_bin, provider, "-M", "json-ocsf", "--output-directory", out_dir]
            if checks:
                cmd += ["-c", checks]
            try:
                subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            except FileNotFoundError:
                raise CSPMScanError(
                    "prowler CLI를 찾을 수 없음. 설치: pip install prowler "
                    "(https://docs.prowler.com/). 로컬 미설치 시 scan_from_json 사용."
                )
            except subprocess.TimeoutExpired:
                raise CSPMScanError("prowler 타임아웃(%ds)" % timeout)

            # compliance/ 서브폴더에도 프레임워크별 *.ocsf.json이 있어 최상위(non-recursive)만 본다.
            candidates = glob.glob(f"{out_dir}/*.ocsf.json")
            if not candidates:
                raise CSPMScanError(
                    "prowler 출력 파일(*.ocsf.json)을 찾을 수 없음 — CLI 실행 자체가 실패했을 수 있음"
                )
            with open(candidates[0], encoding="utf-8") as f:
                items = json.load(f)

        if not isinstance(items, list):
            items = [items]
        # FAIL만 봉투화(정규화부가 status로 open/remediated 판정하지만, 노이즈 최소화)
        # source_format="ocsf" — 위 CLI가 실제로 내놓는 포맷과 일치시킴(정규화부 _parse_ocsf로 라우팅).
        fails = [it for it in items if str(it.get("status_code", "")).upper() == "FAIL"]
        return [self._build_envelope(it, source, "ocsf", cloud) for it in fails]


# ── 헬퍼 ──────────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_batch() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
