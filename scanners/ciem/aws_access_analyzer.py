"""AWS IAM Access Analyzer CIEM 스캐너 (준형 담당) — 역할분담표 원안(project-draft §4.1)의
"스캐너-CIEM: IAM Access Analyzer(AWS)"를 채운다. entra.py(Azure CIEM)와 대칭 구조.

역할:
  IAM Access Analyzer(ACCOUNT 타입, 외부접근 분석기)의 ListFindings 결과 — "외부/퍼블릭에서
  접근 가능한 리소스"(S3·IAM Role·KMS·SQS·SNS·Lambda 등, 신뢰정책·리소스정책 기반 도달성 분석) —
  를 계약⑤ ingest-envelope으로 감싸 반환한다. Prowler가 못 보는 신호(정책 도달성 분석 엔진)라
  실제 CIEM 가치가 있다.

대상 control(계약 control-catalog.json):
  INTERNAL-IAM-OVERPRIV-001(sources에 "access-analyzer:*"가 이미 예비 등록돼 있었음 — 이 스캐너가
  그 자리를 채움. "과도권한"의 CIEM적 의미 = 의도보다 넓게 도달 가능한 접근권)

실배포 스왑:
  scan_access_analyzer() → EventBridge(cnapp.scanner/scan.completed) PutEvents로 발행
  (.github/workflows/access-analyzer-scan.yml, GitHub OIDC 키리스, SecurityAudit로 read).
  이 파일의 봉투화 로직은 무변.

목업용:
  scan_from_json(raw) — Access Analyzer ListFindings 응답 1건(dict)을 직접 주입.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional


class AccessAnalyzerScanError(Exception):
    """Access Analyzer 스캐너 실행 실패(분석기 없음·권한 등)."""


class AccessAnalyzerScanner:
    """IAM Access Analyzer ListFindings 결과 → 계약⑤ ingest-envelope 래퍼.

    mock: scan_from_json()으로 미리 받아둔 finding dict를 봉투화.
    real: scan_access_analyzer()가 boto3로 ACTIVE 분석기를 찾아 findings 조회.
    """

    def __init__(self, region: str = "ap-northeast-2", profile: Optional[str] = None) -> None:
        self._region = region
        self._profile = profile

    # ── 목업용 ────────────────────────────────────────────────────────
    def scan_from_json(self, raw: dict) -> dict:
        """미리 받아둔 Access Analyzer finding(단건) → 계약⑤ ingest-envelope.

        raw는 boto3 accessanalyzer.list_findings() Findings[] 원소 shape 그대로
        (id·resource·resourceType·isPublic·principal·action·status·createdAt 등).
        """
        return self._build_envelope(raw)

    # ── 실 경로(지연 import) ──────────────────────────────────────────
    def scan_access_analyzer(self, analyzer_arn: Optional[str] = None) -> List[dict]:
        """boto3로 ACTIVE 상태 finding을 조회해 계약⑤ 봉투[] 반환(finding 1건=봉투 1개).

        전제: IAM Access Analyzer(type=ACCOUNT, 외부접근 분석기, 무료) 활성화됨
        (infra/shared aws_accessanalyzer_analyzer). analyzer_arn 미지정 시 계정의
        첫 ACTIVE 분석기를 자동 탐색. read-only(access-analyzer:ListAnalyzers/ListFindings).
        """
        try:
            import boto3
        except ImportError as e:  # pragma: no cover
            raise AccessAnalyzerScanError("scan_access_analyzer는 boto3 필요 — pip install boto3") from e

        session = boto3.Session(profile_name=self._profile, region_name=self._region)
        client = session.client("accessanalyzer")

        if not analyzer_arn:
            analyzers = client.list_analyzers(type="ACCOUNT").get("analyzers", [])
            active = [a for a in analyzers if a.get("status") == "ACTIVE"]
            if not active:
                raise AccessAnalyzerScanError(
                    "ACTIVE 상태 ACCOUNT 분석기가 없음 — infra/shared aws_accessanalyzer_analyzer "
                    "apply 필요(무료, 외부접근 분석기)"
                )
            analyzer_arn = active[0]["arn"]

        envelopes: List[dict] = []
        paginator = client.get_paginator("list_findings")
        for page in paginator.paginate(
            analyzerArn=analyzer_arn,
            filter={"status": {"eq": ["ACTIVE"]}},
        ):
            for finding in page.get("findings", []):
                if _is_self_cluster_irsa_noise(finding):
                    continue
                envelopes.append(self._build_envelope(finding))
        return envelopes

    # ── 봉투화 ────────────────────────────────────────────────────────
    def _build_envelope(self, raw: dict) -> dict:
        """계약⑤ ingest-envelope 조립. source="access-analyzer", source_format="custom" 고정."""
        return {
            "envelope_id": str(uuid.uuid4()),
            "source": "access-analyzer",
            "source_format": "custom",
            "cloud_hint": "aws",
            "scan_batch_id": "access-analyzer-%s" % _now_batch(),
            "ingested_at": _now(),
            "raw_inline": raw,
        }


# ── 노이즈 억제 ───────────────────────────────────────────────────────
# 2026-07-08 실측: 이 계정 실 스캔 결과 6건 중 5건이 이 EKS 클러스터 "자기 자신"의 OIDC
# provider(IRSA 패턴 — order-irsa·alb-controller-irsa·karpenter 등)를 신뢰하는 역할이었음.
# Access Analyzer는 Federated(OIDC) principal을 전부 "외부"로 취급하지만, EKS 자체 OIDC
# provider를 신뢰하는 건 IRSA의 정상 설계(이 프로젝트가 의도적으로 채택한 패턴)라 매 스캔마다
# 노이즈만 쌓인다. GitHub Actions OIDC(token.actions.githubusercontent.com)처럼 클러스터
# 외부의 진짜 제3자 신원은 그대로 남긴다(kube-bench의 "매핑 안 되고 PASS면 finding 안 만듦"과
# 같은 철학 — 알려진 정상 패턴은 스캐너 단계에서 걸러 콘솔 노이즈를 줄인다).
def _is_self_cluster_irsa_noise(finding: dict) -> bool:
    principal = finding.get("principal") or {}
    fed = principal.get("Federated", "")
    return isinstance(fed, str) and "oidc.eks." in fed and ".amazonaws.com" in fed


# ── 헬퍼 ──────────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_batch() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


# ── CLI 간이 사용 (python -m scanners.ciem.aws_access_analyzer) ─────────
def _cli_main() -> int:
    import json
    import sys

    scanner = AccessAnalyzerScanner()
    try:
        envelopes = scanner.scan_access_analyzer()
    except AccessAnalyzerScanError as e:
        print("오류:", e, file=sys.stderr)
        return 1

    print(json.dumps(envelopes, ensure_ascii=False, indent=2, default=str))  # datetime → str(boto3 응답)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
