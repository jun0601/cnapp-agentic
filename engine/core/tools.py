"""Read-only 툴 실행기 (계약④ allowlist 강제).

Evidence 에이전트가 '스스로 호출'하는 read-only API. 핵심 = 챗봇 탈출 기준(tool use).
- allowlist(계약④) 밖 툴 호출은 차단(거버넌스 — read-only first, 변경 API 금지).
- 목업: MockToolExecutor가 골든 리소스에 canned 응답 반환(실 AWS/Graph 대신).
- 실배포: RealToolExecutor(boto3 / MS Graph)로 교체 — Evidence 로직은 무변(같은 인터페이스).
"""
from __future__ import annotations

import json
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


def _principal_is_public(principal) -> bool:
    """S3 버킷 정책 statement의 Principal이 공개(*)인지."""
    if principal == "*":
        return True
    if isinstance(principal, dict):
        aws = principal.get("AWS")
        if aws == "*":
            return True
        if isinstance(aws, list) and "*" in aws:
            return True
    return False


class RealToolExecutor(ToolExecutor):
    """실 AWS read-only 실행기 — MockToolExecutor와 '동일 인터페이스', boto3로 실제 호출.

    vertical slice(엔진 실 tool-use 증명)용. Orchestrator/Evidence에서 Mock 대신 이걸 주입하면
    조사 로직 무변으로 실 AWS를 조사한다(계약이 SSOT라 스왑 매끄러움). allowlist 강제는
    base(ToolExecutor._check)가 담당 — read-only first 거버넌스가 실 호출에도 그대로 적용.

    slice 범위 = **무료 S3 read-only만 실구현**(`s3:GetBucketPolicy`·`s3:GetPublicAccessBlock`).
    macie2/iam/ec2는 비용·범위상 미구현(NotImplementedError) — 필요 시 핸들러 추가로 확장.

    boto3/botocore는 **지연 import** — 미설치 환경에서도 MockToolExecutor·run_demo가 안 깨지게.
    """

    def __init__(self, region: str = "ap-northeast-2", profile: Optional[str] = None) -> None:
        super().__init__()  # allowlist 로드(계약④)
        try:
            import boto3
            from botocore.exceptions import ClientError
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("RealToolExecutor는 boto3 필요 — pip install boto3") from e
        self._ClientError = ClientError
        session = boto3.Session(profile_name=profile, region_name=region)
        self._s3 = session.client("s3")

    @staticmethod
    def _bucket_name(resource_id: str) -> str:
        # resource_id 캐논(4.4.1a): {cloud}:{type}:{native_id} — s3_bucket이면 native_id=버킷명
        parts = resource_id.split(":", 2)
        if len(parts) != 3 or parts[1] != "s3_bucket":
            raise ValueError("S3 버킷 resource_id 아님: %s" % resource_id)
        return parts[2]

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def execute(self, tool: str, resource_id: str) -> ToolResult:
        self._check(tool)  # ★ allowlist 강제(base) — 변경/쓰기 API면 여기서 차단
        handler = {
            "s3:GetBucketPolicy": self._get_bucket_policy,
            "s3:GetPublicAccessBlock": self._get_public_access_block,
        }.get(tool)
        if handler is None:
            raise NotImplementedError(
                "'%s'는 실 slice 미구현(무료 S3 read-only만 구현) — 핸들러 추가로 확장." % tool
            )
        return handler(tool, resource_id)

    def _get_bucket_policy(self, tool: str, resource_id: str) -> ToolResult:
        bucket = self._bucket_name(resource_id)
        try:
            resp = self._s3.get_bucket_policy(Bucket=bucket)
            policy = json.loads(resp["Policy"])
        except self._ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchBucketPolicy":
                return ToolResult(tool, resource_id, "버킷 정책 없음 — 공개 statement 미발견",
                                  False, {}, self._now())
            raise
        public = any(
            s.get("Effect") == "Allow" and _principal_is_public(s.get("Principal"))
            for s in policy.get("Statement", [])
        )
        summary = ('Principal:"*" 허용 statement 확인 — 공개 버킷'
                   if public else "공개 Principal statement 없음")
        return ToolResult(tool, resource_id, summary, public, policy, self._now())

    def _get_public_access_block(self, tool: str, resource_id: str) -> ToolResult:
        bucket = self._bucket_name(resource_id)
        try:
            resp = self._s3.get_public_access_block(Bucket=bucket)
            cfg = resp["PublicAccessBlockConfiguration"]
        except self._ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchPublicAccessBlockConfiguration":
                # PAB 미설정 = 공개 차단이 아예 없음(위험)
                return ToolResult(tool, resource_id, "public access block 미설정(차단 없음)",
                                  True, {}, self._now())
            raise
        blocked = bool(cfg.get("BlockPublicAcls")) and bool(cfg.get("RestrictPublicBuckets"))
        summary = ("BlockPublicAcls=%s, RestrictPublicBuckets=%s — %s"
                   % (cfg.get("BlockPublicAcls"), cfg.get("RestrictPublicBuckets"),
                      "차단됨" if blocked else "public access block 미설정"))
        return ToolResult(tool, resource_id, summary, not blocked, cfg, self._now())
