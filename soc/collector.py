"""SOC 확장 훅 — GuardDuty 런타임 위협 탐지 수집기 (코어 CNAPP과 분리).

⚠️ 이 모듈은 핵심 파이프라인과 의도적으로 분리돼 있다:
  - contracts/ 스키마를 import/생성하지 않는다 (SOC event ≠ CNAPP finding)
  - pipeline·engine·RDS에 아무것도 쓰지 않는다 (read-only 수집·표시만)
  - control-catalog·console을 건드리지 않는다

── 왜 분리했나 (2026-07-24 스코프 판단) ─────────────────────────────
이 프로젝트는 시작할 때 CSPM vs SOC 중 **CSPM을 골라 CNAPP로 확장**했고,
SOC(실시간 위협탐지)는 CLAUDE.md에 "범위 밖(확장 훅만)"으로 명시돼 있었다.
GuardDuty를 코어 Findings에 넣으려다 세 군데서 계속 어긋났는데, 그게 전부
같은 경계를 가리켰다:
  ① scanners/ 의 다른 도구(Prowler·Trivy·kube-bench)는 "지금 설정이 올바른가"를
     점검하는 정적 스캔인데, GuardDuty는 상시 돌며 실제 이상행동을 잡는 실시간
     감시라 "스캐너"가 아니다.
  ② CSPM 포스처(6기둥) 어디에도 안 맞는다 — 성격이 다른 축(detection).
  ③ Findings 탭 자체가 "고치면 사라짐(open→remediated)" 모델인데, GuardDuty가
     잡은 건 "그 순간 일어난 사건"이라 이 모델에 안 맞는다.
→ 코어엔 넣지 않되, "SOC 확장 훅이 실제로 작동한다"만 이 독립 데모로 증명한다.

── 실증 (2026-07-24) ───────────────────────────────────────────────
AWS 공식 테스트 도메인(guarddutyc2activityb.com)을 EKS 파드에서 DNS 조회 →
약 4분 만에 실 GuardDuty finding 생성(`Backdoor:EC2/C&CActivity.B!DNS`,
Severity 8.0/High, 샘플 API 아닌 100% 실 탐지). soc/fixtures/ 의 픽스처가 그 실
finding 구조다.

── 사용 ────────────────────────────────────────────────────────────
mock-first (실 계정 없이 CI/데모):
    collect_from_json(raw_findings) — GuardDuty get-findings 원본 → SocEvent[]
실 경로 (지연 import — boto3 미설치/무자격 환경에서도 이 모듈 import는 안전):
    collect() — boto3 guardduty list_detectors→list_findings→get_findings (read-only)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class SocEvent:
    """SOC 런타임 위협 "사건" — CNAPP finding과 다른 모델.

    핵심 차이(코어 경계를 코드로 드러냄):
      · severity_score : GuardDuty 0.0~8.9 스케일 (CNAPP severity_id 1~5와 다름)
      · detected_at    : 사건이 일어난 시각. 불변 — "고치면 사라지는" 대상이 아니다.
      · status/attack_path_id 같은 CNAPP finding 필드를 일부러 갖지 않는다.
    """

    event_id: str
    detected_at: str            # ISO8601 — 사건 발생 시각(불변)
    threat_type: str            # 예: Backdoor:EC2/C&CActivity.B!DNS
    severity_score: float       # GuardDuty 0.0~8.9 (CNAPP 1~5 아님)
    severity_label: str         # Info/Low/Medium/High (GuardDuty 기준)
    title: str
    description: str
    resource: str               # 영향 리소스 식별자 (예: i-032248fc3da6b8e33)
    resource_type: str          # 예: Instance / AccessKey / S3Bucket
    indicator: str              # IOC — C2 도메인·원격 IP 등
    action_type: str            # 예: DNS_REQUEST / NETWORK_CONNECTION / AWS_API_CALL
    observed_count: int         # 관측 횟수
    region: str
    account_id: str
    source: str = "guardduty"
    kind: str = "runtime-threat-event"   # CNAPP finding이 아니라 SOC 사건임을 명시

    def to_dict(self) -> dict:
        return asdict(self)


class GuardDutyCollector:
    """GuardDuty finding → SocEvent 변환 수집기.

    mock: collect_from_json()으로 미리 받아둔 get-findings 원본을 변환(CI/데모).
    real: collect()로 실 계정을 read-only 수집(list/get findings만, 쓰기 없음).
    """

    def __init__(self, region: str = "ap-northeast-2") -> None:
        self._region = region

    # ── 변환 (원본 구조 → SocEvent) ─────────────────────────────────
    def collect_from_json(self, raw_findings: Optional[list]) -> List[SocEvent]:
        """GuardDuty get-findings의 Findings[] 원본 리스트 → SocEvent[]."""
        return [self._to_event(f) for f in (raw_findings or [])]

    def collect(self) -> List[SocEvent]:
        """실 GuardDuty를 read-only로 수집 → SocEvent[].

        boto3는 지연 import — 미설치/무자격 환경에서도 이 모듈 자체 import는 안전.
        아카이브되지 않은(활성) finding만 가져온다.
        """
        import boto3  # 지연 import

        gd = boto3.client("guardduty", region_name=self._region)
        detectors = gd.list_detectors().get("DetectorIds", [])
        if not detectors:
            return []
        detector_id = detectors[0]

        criteria = {"Criterion": {"service.archived": {"Eq": ["false"]}}}
        finding_ids = gd.list_findings(
            DetectorId=detector_id, FindingCriteria=criteria
        ).get("FindingIds", [])

        events: List[SocEvent] = []
        for i in range(0, len(finding_ids), 50):  # get_findings는 배치 50개 상한
            chunk = finding_ids[i:i + 50]
            if not chunk:
                continue
            res = gd.get_findings(DetectorId=detector_id, FindingIds=chunk)
            for f in res.get("Findings", []):
                events.append(self._to_event(f))
        return events

    # ── 내부 매핑 ───────────────────────────────────────────────────
    def _to_event(self, f: dict) -> SocEvent:
        service = f.get("Service", {}) or {}
        action = service.get("Action", {}) or {}
        resource = f.get("Resource", {}) or {}
        score = float(f.get("Severity", 0.0) or 0.0)
        return SocEvent(
            event_id=f.get("Id", ""),
            detected_at=service.get("EventFirstSeen") or f.get("CreatedAt", ""),
            threat_type=f.get("Type", ""),
            severity_score=score,
            severity_label=self._severity_label(score),
            title=f.get("Title", ""),
            description=f.get("Description", ""),
            resource=self._extract_resource(resource),
            resource_type=resource.get("ResourceType", ""),
            indicator=self._extract_indicator(action),
            action_type=action.get("ActionType", ""),
            observed_count=int(service.get("Count", 0) or 0),
            region=f.get("Region", self._region),
            account_id=f.get("AccountId", ""),
        )

    @staticmethod
    def _severity_label(score: float) -> str:
        # GuardDuty 공식 구간: High 7.0~8.9 / Medium 4.0~6.9 / Low 1.0~3.9
        if score >= 7.0:
            return "High"
        if score >= 4.0:
            return "Medium"
        if score >= 1.0:
            return "Low"
        return "Info"

    @staticmethod
    def _extract_resource(resource: dict) -> str:
        rt = resource.get("ResourceType", "")
        if rt == "Instance":
            return resource.get("InstanceDetails", {}).get("InstanceId", "")
        if rt == "AccessKey":
            return resource.get("AccessKeyDetails", {}).get("AccessKeyId", "")
        if rt == "S3Bucket":
            buckets = resource.get("S3BucketDetails", []) or []
            return buckets[0].get("Name", "") if buckets else ""
        return rt or "unknown"

    @staticmethod
    def _extract_indicator(action: dict) -> str:
        at = action.get("ActionType", "")
        if at == "DNS_REQUEST":
            return action.get("DnsRequestAction", {}).get("Domain", "")
        if at == "NETWORK_CONNECTION":
            rid = action.get("NetworkConnectionAction", {}).get("RemoteIpDetails", {})
            return rid.get("IpAddressV4", "")
        if at == "AWS_API_CALL":
            aca = action.get("AwsApiCallAction", {})
            rid = aca.get("RemoteIpDetails", {})
            return rid.get("IpAddressV4", "") or aca.get("Api", "")
        if at == "PORT_PROBE":
            pd = action.get("PortProbeAction", {}).get("PortProbeDetails", []) or []
            if pd:
                return pd[0].get("RemoteIpDetails", {}).get("IpAddressV4", "")
        return ""
