"""Read-only 툴 실행기 (계약④ allowlist 강제).

Evidence 에이전트가 '스스로 호출'하는 read-only API. 핵심 = 챗봇 탈출 기준(tool use).
- allowlist(계약④) 밖 툴 호출은 차단(거버넌스 — read-only first, 변경 API 금지).
- 목업: MockToolExecutor가 골든 리소스에 canned 응답 반환(실 AWS/Graph 대신).
- 실배포: RealToolExecutor(boto3 / MS Graph)로 교체 — Evidence 로직은 무변(같은 인터페이스).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from .contracts import load_allowlist


@dataclass
class ToolResult:
    tool: str
    resource_id: str
    result_summary: str
    confirms: bool  # 이 증거가 위험 가설을 '뒷받침'하는가(신뢰도 계산용)
    raw: dict = field(default_factory=dict)
    ts: str = ""

    def to_evidence_item(self) -> dict:
        """계약⑦ case.evidence[] 항목 형태로."""
        return {
            "tool": self.tool,
            "resource_id": self.resource_id,
            "result_summary": self.result_summary,
            "raw": self.raw,
            "ts": self.ts,
        }


class ToolNotAllowed(Exception):
    """allowlist(계약④) 밖 호출 시도 — 엔진이 차단."""


class ToolExecutor:
    """read-only 툴 실행 인터페이스. Mock/Real이 구현."""

    def __init__(self) -> None:
        al = load_allowlist()
        self.allowlist = set(al["aws"]) | set(al["azure"])

    def _check(self, tool: str) -> None:
        if tool not in self.allowlist:
            raise ToolNotAllowed(
                "'%s'는 read-only allowlist(계약④)에 없음 — 차단. 변경/쓰기 API 금지." % tool
            )

    def execute(self, tool: str, resource_id: str) -> ToolResult:
        raise NotImplementedError


# 목업 canned 응답: (tool, resource_id) → (요약, confirms, raw)
# 골든 시나리오(member 공개 S3·PII + order 과도 IRSA)를 재현. mock-cases.json과 정합.
_CANNED: Dict[Tuple[str, str], Tuple[str, bool, dict]] = {
    ("s3:GetBucketPolicy", "aws:s3_bucket:member-pii-prod"): (
        'Principal:"*" 허용 statement 확인 — 공개 버킷',
        True,
        {"Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject"}]},
    ),
    ("s3:GetPublicAccessBlock", "aws:s3_bucket:member-pii-prod"): (
        "BlockPublicAcls=false, RestrictPublicBuckets=false — public access block 미설정",
        True,
        {"BlockPublicAcls": False, "RestrictPublicBuckets": False},
    ),
    ("macie2:GetFindings", "aws:s3_bucket:member-pii-prod"): (
        "SensitiveData:PII 분류 결과 존재(이름·주민등록번호 패턴 다수)",
        True,
        {"category": "SensitiveData:PII", "count": 200},
    ),
    ("iam:SimulatePrincipalPolicy", "aws:iam_role:order-irsa"): (
        "order-irsa가 s3:GetObject on arn:aws:s3:::member-pii-prod/* 허용 — 측면이동 경로 확인",
        True,
        {"EvalDecision": "allowed", "Action": "s3:GetObject", "Resource": "member-pii-prod/*"},
    ),
    ("ec2:DescribeSecurityGroups", "aws:security_group:sg-0product1234"): (
        "인바운드 0.0.0.0/0 (all ports) 규칙 확인 — 인터넷 개방",
        True,
        {"IpPermissions": [{"IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]},
    ),
}


class MockToolExecutor(ToolExecutor):
    """목업 실행기 — 골든 리소스는 canned 응답, 그 외는 '특이사항 없음'."""

    def __init__(self, base_ts: Optional[datetime] = None) -> None:
        super().__init__()
        self._t = base_ts or datetime(2026, 6, 30, 2, 3, 10, tzinfo=timezone.utc)
        self._seq = 0

    def _next_ts(self) -> str:
        # 호출마다 +3초(데모 타임라인). timedelta로 분/시 캐리 → 단조 증가·충돌 없음(16회+ 안전)
        ts = self._t + timedelta(seconds=self._seq * 3)
        self._seq += 1
        return ts.strftime("%Y-%m-%dT%H:%M:%SZ")

    def execute(self, tool: str, resource_id: str) -> ToolResult:
        self._check(tool)  # allowlist 강제
        summary, confirms, raw = _CANNED.get(
            (tool, resource_id), ("특이사항 없음(정상)", False, {})
        )
        return ToolResult(
            tool=tool,
            resource_id=resource_id,
            result_summary=summary,
            confirms=confirms,
            raw=raw,
            ts=self._next_ts(),
        )
