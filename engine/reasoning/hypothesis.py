"""Hypothesis 에이전트 (진우 담당) — escalated finding에서 가설 자동 생성.

목업: control_id 기반 템플릿 플래너로 가설 생성.
실배포 스왑: generate() 내부 템플릿 로직을 Bedrock Haiku LLM 호출로 교체 —
  LLM이 finding 텍스트·control·resource_id를 읽고 가설 도출(로직 무변, 출력 형태 동일).
"""
from __future__ import annotations

from typing import List

# control_id → 가설 템플릿. {rid} = resource_id placeholder.
_HYPOTHESIS_BY_CONTROL = {
    "INTERNAL-S3-PUBLIC-001":
        "{rid} 버킷이 실제 public 접근을 허용하면 외부 공격자가 데이터를 직접 탈취할 수 있다",
    "INTERNAL-DATA-PII-EXPOSED-001":
        "{rid} 버킷에 PII(주민등록번호·이름 등)가 실존하면 데이터 탈취 경로(R4)가 확증된다",
    "INTERNAL-IAM-OVERPRIV-001":
        "{rid} 역할이 PII 버킷에 s3:* 권한을 보유하면 order→member 측면이동(R2)이 가능하다",
    "INTERNAL-SG-OPEN-INGRESS-001":
        "{rid} 보안그룹이 0.0.0.0/0 인바운드를 허용하면 외부에서 product 파드에 직접 접근할 수 있다",
    "INTERNAL-SECRET-PLAINTEXT-001":
        "{rid}에 평문 노출된 Azure SP 자격증명이 유효하면 크로스클라우드(Azure Entra) 장악으로 번진다",
    "INTERNAL-ENTRA-SP-CRED-001":
        "{rid} SP의 만료 없는 자격증명이 탈취되면 Azure 디렉터리 영구 접근이 가능하다",
    "INTERNAL-ENTRA-INSECURE-CFG-001":
        "{rid} Entra 앱이 과도한 디렉터리 권한을 보유하면 전체 조직 신원 정보를 열람할 수 있다",
    "INTERNAL-ECR-SCAN-DISABLED-001":
        "{rid} 이미지에 CVE가 포함될 때 scan-on-push 비활성이면 취약 이미지가 그대로 배포된다",
    "INTERNAL-S3-LOGGING-DISABLED-001":
        "{rid} 버킷의 접근 로그가 없으면 탈취 이후 포렌식이 불가능하다",
}

# attack_path에 cross_cloud edge가 있을 때 추가하는 크로스클라우드 체인 가설
_CROSS_CLOUD_HYPOTHESIS = (
    "AWS 워크로드 침해(S3 PII 탈취) → 평문 Azure SP 자격증명 → "
    "Entra 디렉터리 장악으로 이어지는 크로스클라우드 공격 체인이 성립한다"
)


def _has_cross_cloud(paths: List[dict]) -> bool:
    # 계약③ 엣지는 type(lateral_move·credential_theft…) + cross_cloud(불리언) 구조.
    # "cross_cloud" 라는 edge type은 없음 → 경계 횡단 여부는 cross_cloud 플래그로 판정.
    for p in paths:
        for edge in p.get("edges", []):
            if edge.get("cross_cloud"):
                return True
    return False


class HypothesisAgent:
    """escalated finding + attack_path → 검증 가설[] 생성.

    실배포 스왑: generate() 내 템플릿 플래너를 Bedrock Haiku LLM 호출로 교체.
    인터페이스(입출력 형태)는 동일하게 유지한다.
    """

    # orchestrator가 호출 후 읽는 관측용 속성(계약 밖 부가 정보) — 템플릿은 LLM 미사용이라
    # 항상 0/템플릿 라벨. BedrockHypothesisAgent는 동일 이름 속성을 실사용량으로 갱신한다.
    last_tokens = (0, 0)
    model_label = "template"

    def generate(self, findings: List[dict], paths: List[dict]) -> List[str]:
        """finding 목록과 attack_path에서 검증 가설 목록을 생성한다."""
        seen = set()  # type: ignore[var-annotated]
        hypotheses = []  # type: List[str]

        for f in findings:
            ctrl = f.get("control_id", "")
            rid = f.get("resource_id", "")
            template = _HYPOTHESIS_BY_CONTROL.get(ctrl)
            if not template:
                continue
            hyp = template.format(rid=rid)
            if hyp not in seen:
                seen.add(hyp)
                hypotheses.append(hyp)

        # 크로스클라우드 체인 가설 — attack_path에 cross_cloud edge 있을 때
        if _has_cross_cloud(paths) and _CROSS_CLOUD_HYPOTHESIS not in seen:
            hypotheses.append(_CROSS_CLOUD_HYPOTHESIS)

        # 가설이 하나도 없으면 범용 fallback
        if not hypotheses:
            hypotheses.append(
                "escalated finding의 위험이 실제 환경에서도 재현 가능한지 확인이 필요하다"
            )

        return hypotheses
