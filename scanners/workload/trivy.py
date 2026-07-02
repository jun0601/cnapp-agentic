"""Trivy 워크로드 스캐너 (진우 담당).

역할:
  컨테이너 이미지를 Trivy CLI로 스캔하고,
  결과를 계약⑤ ingest-envelope으로 감싸 반환한다.
  이후 Normalizer(pipeline/normalize)가 envelope → 계약① finding 변환.

흐름:
  TrivyScanner.scan_image("shop/product:latest")
      ├─ trivy image --format json --quiet <image>  실행
      └─ _build_envelope(raw_json, image) → 계약⑤ envelope

실배포 스왑:
  ECR push 이벤트(EventBridge) → Lambda → scan_image() →
  envelope을 SQS(ingest 큐)로 publish → 정규화 Lambda가 처리.
  이 파일의 스캔·봉투화 로직은 무변.

목업용:
  scan_from_json(trivy_json, image) — Trivy CLI 없이 JSON 직접 주입.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Optional


class TrivyScanError(Exception):
    """Trivy CLI 실행 실패."""


class TrivyScanner:
    """Trivy 이미지 스캐너 래퍼.

    Trivy CLI가 설치된 환경에서는 scan_image()로 실 스캔.
    CI/테스트에서는 scan_from_json()으로 미리 받아둔 JSON을 봉투화.
    """

    def __init__(self, trivy_bin: str = "trivy") -> None:
        self._bin = trivy_bin

    # ── 실 스캔 (trivy CLI 필요) ───────────────────────────────────────

    def scan_image(
        self,
        image: str,
        severity: str = "CRITICAL,HIGH,MEDIUM",
        timeout: int = 180,
    ) -> dict:
        """Trivy CLI로 이미지 스캔 → 계약⑤ ingest-envelope.

        Args:
            image:    스캔 대상 이미지 (예: "shop/product:latest",
                      "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/product:latest")
            severity: 포함할 심각도 필터 (trivy --severity)
            timeout:  trivy 프로세스 최대 대기 시간(초)

        Returns:
            계약⑤ ingest-envelope dict (raw_inline = trivy JSON 원본)

        Raises:
            TrivyScanError: trivy 미설치 또는 실행 실패
        """
        raw = self._run_trivy(image, severity, timeout)
        return self._build_envelope(raw, image)

    def _run_trivy(self, image: str, severity: str, timeout: int) -> dict:
        cmd = [
            self._bin, "image",
            "--format", "json",
            "--quiet",          # 진행 로그 억제
            "--severity", severity,
            image,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            raise TrivyScanError(
                "trivy CLI를 찾을 수 없음.\n"
                "설치: https://trivy.dev/latest/getting-started/installation/\n"
                "또는: brew install trivy  /  apt install trivy"
            )
        except subprocess.TimeoutExpired:
            raise TrivyScanError("trivy 타임아웃(%ds) — 이미지가 너무 크거나 네트워크 문제" % timeout)

        if result.returncode != 0:
            # trivy는 취약점 발견 시 exit 1 반환하는 경우도 있음 — stdout에 JSON이 있으면 정상
            if result.stdout.strip():
                pass  # JSON 있으면 경고 수준, 계속 진행
            else:
                raise TrivyScanError(
                    "trivy 실패 (exit %d): %s" % (result.returncode, result.stderr[:500])
                )

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise TrivyScanError("trivy 출력 JSON 파싱 실패: %s" % e)

    # ── 목업용 ────────────────────────────────────────────────────────

    def scan_from_json(self, trivy_json: dict, image: str) -> dict:
        """미리 받아둔 Trivy JSON을 계약⑤ ingest-envelope으로 감싸기.

        Trivy CLI 없이 run_demo / CI에서 end-to-end 흐름을 검증할 때 사용.
        """
        return self._build_envelope(trivy_json, image)

    # ── 봉투화 ────────────────────────────────────────────────────────

    def _build_envelope(self, raw: dict, image: str) -> dict:
        """계약⑤ ingest-envelope 조립.

        source="trivy", source_format="trivy-json" 고정.
        scan_batch_id는 이미지명+스캔 시각 — remediated 판정 스코프(4.4.1c)에 사용.
        """
        safe_img = image.replace(":", "-").replace("/", "-")
        return {
            "envelope_id": str(uuid.uuid4()),
            "source": "trivy",
            "source_format": "trivy-json",
            "cloud_hint": "aws",
            "scan_batch_id": "trivy-%s-%s" % (safe_img, _now_batch()),
            "ingested_at": _now(),
            "raw_inline": raw,
        }


# ── 헬퍼 ──────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _now_batch() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


# ── CLI 간이 사용 (python -m scanners.workload.trivy <image>) ──────────

def _cli_main() -> int:
    import sys
    if len(sys.argv) < 2:
        print("사용법: python -m scanners.workload.trivy <image>", file=sys.stderr)
        return 1
    image = sys.argv[1]
    scanner = TrivyScanner()
    try:
        envelope = scanner.scan_image(image)
    except TrivyScanError as e:
        print("오류:", e, file=sys.stderr)
        return 1

    # 봉투만 출력 (정규화는 pipeline/normalize에 위임)
    print(json.dumps(envelope, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
