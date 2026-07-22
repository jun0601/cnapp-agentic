"""Read-only 툴 실행기 (계약④ allowlist 강제).

Evidence 에이전트가 '스스로 호출'하는 read-only API. 핵심 = 챗봇 탈출 기준(tool use).
- allowlist(계약④) 밖 툴 호출은 차단(거버넌스 — read-only first, 변경 API 금지).
- 목업: MockToolExecutor가 골든 리소스에 canned 응답 반환(실 AWS/Graph 대신).
- 실배포: RealToolExecutor(boto3 / MS Graph)로 교체 — Evidence 로직은 무변(같은 인터페이스).
"""
from __future__ import annotations

import json
import re
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

    def executable_apis(self) -> List[str]:
        """이 실행기가 **실제로 호출할 수 있는** API 목록.

        allowlist(계약④)는 '허용 경계'이지 '구현 목록'이 아니다 — 둘을 구분해야 한다.
        계약④의 azure_ms_graph 항목은 API 이름이 아니라 **Graph 권한 스코프**
        (Application.Read.All 등)이고 대응 핸들러도 없다. 그런데 LLM 플래너가
        allowlist를 그대로 tool enum으로 넘기면 **LLM이 호출 불가능한 것을 고를 수 있고**,
        매 시도가 실패로 낭비된다(2026-07-21 발견). 그래서 플래너는 allowlist가 아니라
        이 목록을 enum으로 쓴다. allowlist 강제(_check)는 그대로 유지 — 경계는 안 넓어진다.
        """
        return sorted(self.allowlist)


# 목업 canned 응답: (tool, resource_id) → (요약, confirms, raw)
# 골든 시나리오(member 공개 S3·PII + order 과도 IRSA)를 재현. mock-cases.json과 정합.
_CANNED: Dict[Tuple[str, str], Tuple[str, bool, dict]] = {
    ("s3:GetBucketPolicy", "aws:s3_bucket:member-pii-prod"): (
        'Principal:"*" 허용 statement 확인 — 공개 버킷',
        True,
        {"Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject"}]},
    ),
    ("s3:GetBucketPublicAccessBlock", "aws:s3_bucket:member-pii-prod"): (
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

    Orchestrator/Evidence에서 Mock 대신 이걸 주입하면 조사 로직 무변으로 실 AWS를 조사한다
    (계약이 SSOT라 스왑 매끄러움). allowlist 강제는 base(ToolExecutor._check)가 담당 —
    read-only first 거버넌스가 실 호출에도 그대로 적용.

    구현 범위(2026-07-04 allowlist AWS 전종으로 확장 — 골든 경로 f3·f4·f6·f7 실조사 가능):
      s3:GetBucketPolicy · GetBucketAcl · GetBucketPublicAccessBlock  (f6 공개 S3)
      ec2:DescribeSecurityGroups                                 (f3 개방 SG)
      iam:SimulatePrincipalPolicy · ListAttachedRolePolicies · GetRolePolicy  (f4 과도 IRSA)
      macie2:GetFindings · access-analyzer:ListFindings           (f7 PII·외부접근 — 서비스 미활성이면
                                                                  크래시 대신 중립 결과로 우아하게 강등)
    Azure(MS Graph) 툴은 미구현 — 골든 데모 조사 범위는 AWS(§9 UC0), Azure는 finding 소스로만.

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
        self._session = boto3.Session(profile_name=profile, region_name=region)
        self._clients: Dict[str, object] = {}  # 서비스별 지연 생성(안 쓰는 클라이언트 초기화 비용 회피)

    def _client(self, service: str):
        if service not in self._clients:
            self._clients[service] = self._session.client(service)
        return self._clients[service]

    @property
    def _s3(self):  # 기존 호출부(run_real 등) 호환
        return self._client("s3")

    @staticmethod
    def _native(resource_id: str, expected_type: str) -> str:
        # resource_id 캐논(4.4.1a): {cloud}:{type}:{native_id}
        parts = resource_id.split(":", 2)
        if len(parts) != 3 or parts[1] != expected_type:
            raise ValueError("%s resource_id 아님: %s" % (expected_type, resource_id))
        return parts[2]

    @classmethod
    def _bucket_name(cls, resource_id: str) -> str:
        return cls._native(resource_id, "s3_bucket")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _handlers(self) -> dict:
        """실제 구현된 read-only 핸들러 — AWS 9종. Azure(MS Graph)는 미구현.

        Azure를 안 넣은 이유(의도적 범위): 계약④의 azure_ms_graph는 API 이름이 아니라
        **Graph 권한 스코프**이고, Lambda에서 Graph를 호출하려면 Entra 자격증명이 필요한데
        그건 키리스 원칙(D4)과 충돌한다. 골든 데모의 조사 범위는 AWS(§9 UC0)이고
        Azure는 finding 소스로만 쓴다 — 그 경계를 executable_apis()로 명시한다.
        """
        return {
            "s3:GetBucketPolicy": self._get_bucket_policy,
            "s3:GetBucketAcl": self._get_bucket_acl,
            "s3:GetBucketPublicAccessBlock": self._get_public_access_block,
            "ec2:DescribeSecurityGroups": self._describe_security_groups,
            "iam:SimulatePrincipalPolicy": self._simulate_principal_policy,
            "iam:ListAttachedRolePolicies": self._list_attached_role_policies,
            "iam:GetRolePolicy": self._get_role_policy,
            "macie2:GetFindings": self._macie_get_findings,
            "access-analyzer:ListFindings": self._accessanalyzer_list_findings,
        }

    def executable_apis(self) -> List[str]:
        """LLM 플래너에 노출할 '실제로 호출 가능한' API — allowlist ∩ 구현된 핸들러."""
        return sorted(set(self._handlers()) & self.allowlist)

    def execute(self, tool: str, resource_id: str) -> ToolResult:
        self._check(tool)  # ★ allowlist 강제(base) — 변경/쓰기 API면 여기서 차단
        handler = self._handlers().get(tool)
        if handler is None:
            raise NotImplementedError(
                "'%s'는 실 실행기 미구현(AWS allowlist 9종만) — 핸들러 추가로 확장." % tool
            )
        return handler(tool, resource_id)

    def _no_bucket(self, tool: str, resource_id: str) -> ToolResult:
        """버킷이 존재하지 않을 때(NoSuchBucket) 중립 결과. 조사 전체를 크래시시키지 않는다
        (2026-07-04 라이브 실측: 버킷 하나 없으면 GetBucketAcl 등이 예외를 던져 investigate가 죽음)."""
        return ToolResult(tool, resource_id, "버킷이 존재하지 않음(NoSuchBucket) — 이 증거는 생략",
                          False, {"error": "NoSuchBucket"}, self._now())

    def _get_bucket_policy(self, tool: str, resource_id: str) -> ToolResult:
        bucket = self._bucket_name(resource_id)
        try:
            resp = self._s3.get_bucket_policy(Bucket=bucket)
            policy = json.loads(resp["Policy"])
        except self._ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "NoSuchBucket":
                return self._no_bucket(tool, resource_id)
            if code == "NoSuchBucketPolicy":
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
            code = e.response["Error"]["Code"]
            if code == "NoSuchBucket":
                return self._no_bucket(tool, resource_id)
            if code == "NoSuchPublicAccessBlockConfiguration":
                # PAB 미설정 = 공개 차단이 아예 없음(위험)
                return ToolResult(tool, resource_id, "public access block 미설정(차단 없음)",
                                  True, {}, self._now())
            raise
        blocked = bool(cfg.get("BlockPublicAcls")) and bool(cfg.get("RestrictPublicBuckets"))
        summary = ("BlockPublicAcls=%s, RestrictPublicBuckets=%s — %s"
                   % (cfg.get("BlockPublicAcls"), cfg.get("RestrictPublicBuckets"),
                      "차단됨" if blocked else "public access block 미설정"))
        return ToolResult(tool, resource_id, summary, not blocked, cfg, self._now())

    # ── 2026-07-04 확장: 골든 경로(f3 SG·f4 IRSA·f7 PII) 실조사 핸들러 ──────────

    def _get_bucket_acl(self, tool: str, resource_id: str) -> ToolResult:
        bucket = self._bucket_name(resource_id)
        try:
            resp = self._s3.get_bucket_acl(Bucket=bucket)
        except self._ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchBucket":
                return self._no_bucket(tool, resource_id)
            raise
        # AllUsers/AuthenticatedUsers grantee = ACL 레벨 공개(정책과 별개 공개 표면)
        public_uris = ("http://acs.amazonaws.com/groups/global/AllUsers",
                       "http://acs.amazonaws.com/groups/global/AuthenticatedUsers")
        public_grants = [g for g in resp.get("Grants", [])
                         if g.get("Grantee", {}).get("URI") in public_uris]
        summary = ("AllUsers/AuthenticatedUsers grant %d건 — ACL 공개" % len(public_grants)
                   if public_grants else "공개 grantee 없음(ACL 정상)")
        return ToolResult(tool, resource_id, summary, bool(public_grants),
                          {"Grants": resp.get("Grants", [])}, self._now())

    _SG_ID_RE = re.compile(r"^sg-[0-9a-f]{8}([0-9a-f]{9})?$")

    def _describe_security_groups(self, tool: str, resource_id: str) -> ToolResult:
        sg_id = self._native(resource_id, "security_group")
        if not self._SG_ID_RE.match(sg_id):
            # 형식 자체가 실 AWS SG ID(16진수 8자리 또는 17자리)가 아니면 API 호출 자체를
            # 스킵 — 어차피 InvalidGroupId.Malformed로 실패할 게 확실하고, X-Ray는 HTTP 4xx
            # 응답이 오는 순간 그 서브세그먼트를 자동으로 Error 표시해서(내 코드가 예외를
            # 나중에 잡아도 안 지워짐) 호출 자체를 안 해야 깨끗하게 관측됨(2026-07-21).
            return ToolResult(tool, resource_id,
                              "'%s'는 실 AWS 보안그룹 ID 형식이 아님(합성/골든시드 값) — 조회 생략" % sg_id,
                              False, {}, self._now())
        try:
            resp = self._client("ec2").describe_security_groups(GroupIds=[sg_id])
        except self._ClientError as e:
            # 다른 핸들러(S3 NoSuchBucket·Macie·AccessAnalyzer)와 동일한 원칙 — 리소스가
            # 실AWS에 없으면 조사 크래시 대신 중립 결과로 강등(2026-07-21, X-Ray에서 이 핸들러만
            # try/except가 빠져 unhandled fault로 잡히던 걸 발견). 골든시드 합성 SG ID처럼
            # 애초에 실물이 없는 경우 여기로 옴 — confirms=False(위험을 확증도 반증도 못 함).
            code = e.response["Error"]["Code"]
            return ToolResult(tool, resource_id,
                              "보안 그룹 조회 불가(%s) — 이 SG는 실AWS에 존재하지 않음" % code,
                              False, {"error": code}, self._now())
        perms = resp["SecurityGroups"][0].get("IpPermissions", []) if resp.get("SecurityGroups") else []
        open_rules = []
        for p in perms:
            open_v4 = any(r.get("CidrIp") == "0.0.0.0/0" for r in p.get("IpRanges", []))
            open_v6 = any(r.get("CidrIpv6") == "::/0" for r in p.get("Ipv6Ranges", []))
            if open_v4 or open_v6:
                port = ("all" if p.get("IpProtocol") == "-1"
                        else "%s-%s" % (p.get("FromPort"), p.get("ToPort")))
                open_rules.append(port)
        summary = ("인바운드 0.0.0.0/0(포트 %s) — 인터넷 개방" % ", ".join(open_rules)
                   if open_rules else "전세계 개방(0.0.0.0/0·::/0) 인바운드 없음")
        return ToolResult(tool, resource_id, summary, bool(open_rules),
                          {"IpPermissions": perms}, self._now())

    def _role_arn(self, role_name: str) -> str:
        acct = self._client("sts").get_caller_identity()["Account"]
        return "arn:aws:iam::%s:role/%s" % (acct, role_name)

    def _simulate_principal_policy(self, tool: str, resource_id: str) -> ToolResult:
        """f4 과도권한의 객관 증거 — '임의 버킷 객체'에 대한 민감 S3 액션이 allowed인가 시뮬레이션."""
        role = self._native(resource_id, "iam_role")
        try:
            resp = self._client("iam").simulate_principal_policy(
                PolicySourceArn=self._role_arn(role),
                ActionNames=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                ResourceArns=["arn:aws:s3:::*/*"],
            )
        except self._ClientError as e:
            code = e.response["Error"]["Code"]
            return ToolResult(tool, resource_id,
                              "역할 조회 불가(%s) — 이 역할은 실AWS에 존재하지 않음" % code,
                              False, {"error": code}, self._now())
        allowed = [r["EvalActionName"] for r in resp.get("EvaluationResults", [])
                   if r.get("EvalDecision") == "allowed"]
        summary = ("%s가 임의 S3 객체에 %s 허용 — 과도권한(측면이동 경로) 확인"
                   % (role, ", ".join(allowed))
                   if allowed else "임의 S3 객체 접근 불허(최소권한 정상)")
        return ToolResult(tool, resource_id, summary, bool(allowed),
                          {"allowed_actions": allowed}, self._now())

    def _list_attached_role_policies(self, tool: str, resource_id: str) -> ToolResult:
        role = self._native(resource_id, "iam_role")
        try:
            resp = self._client("iam").list_attached_role_policies(RoleName=role)
        except self._ClientError as e:
            code = e.response["Error"]["Code"]
            return ToolResult(tool, resource_id,
                              "역할 조회 불가(%s) — 이 역할은 실AWS에 존재하지 않음" % code,
                              False, {"error": code}, self._now())
        names = [p["PolicyName"] for p in resp.get("AttachedPolicies", [])]
        broad = [n for n in names
                 if n in ("AdministratorAccess", "PowerUserAccess", "AmazonS3FullAccess")]
        summary = ("광역 관리형 정책 부착: %s — 과도권한" % ", ".join(broad) if broad
                   else "부착 관리형 정책 %d개(광역 정책 없음): %s" % (len(names), ", ".join(names) or "-"))
        return ToolResult(tool, resource_id, summary, bool(broad),
                          {"AttachedPolicies": names}, self._now())

    # 역할 접미사 → 인라인 정책명 (infra/target 실물과 1:1 — IAM ListRolePolicies는 allowlist 밖이라
    # 이름 열거 대신 알려진 매핑 사용. 매핑 없는 역할이면 중립 결과)
    _INLINE_POLICY_BY_SUFFIX = {"-order-irsa": "order-s3", "-member-irsa": "member-pii-put"}

    def _get_role_policy(self, tool: str, resource_id: str) -> ToolResult:
        role = self._native(resource_id, "iam_role")
        policy_name = next((v for k, v in self._INLINE_POLICY_BY_SUFFIX.items()
                            if role.endswith(k)), None)
        if policy_name is None:
            return ToolResult(tool, resource_id,
                              "인라인 정책명 미상(ListRolePolicies는 allowlist 밖) — 조회 생략",
                              False, {}, self._now())
        try:
            resp = self._client("iam").get_role_policy(RoleName=role, PolicyName=policy_name)
        except self._ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchEntity":
                return ToolResult(tool, resource_id,
                                  "인라인 정책 '%s' 없음" % policy_name, False, {}, self._now())
            raise
        doc = resp.get("PolicyDocument", {})
        stmts = doc.get("Statement", [])
        if isinstance(stmts, dict):
            stmts = [stmts]
        wild = any(
            ("*" in (s.get("Action") if isinstance(s.get("Action"), list) else [s.get("Action")])
             or "s3:*" in (s.get("Action") if isinstance(s.get("Action"), list) else [s.get("Action")]))
            and "*" in (s.get("Resource") if isinstance(s.get("Resource"), list) else [s.get("Resource")])
            for s in stmts if s.get("Effect") == "Allow"
        )
        summary = ("인라인 '%s': s3:*/Action 와일드카드 + Resource:* — 과도권한" % policy_name
                   if wild else "인라인 '%s': 스코프 제한됨(정상)" % policy_name)
        return ToolResult(tool, resource_id, summary, wild, doc, self._now())

    def _macie_get_findings(self, tool: str, resource_id: str) -> ToolResult:
        """PII 탐지(f7). Macie 미활성/권한 부족이면 크래시 대신 중립 결과(라이브 강건성)."""
        bucket = self._bucket_name(resource_id)
        m = self._client("macie2")
        try:
            ids = m.list_findings(findingCriteria={"criterion": {
                "resourcesAffected.s3Bucket.name": {"eq": [bucket]}}}, maxResults=10).get("findingIds", [])
            if not ids:
                return ToolResult(tool, resource_id, "Macie finding 없음(해당 버킷)", False, {}, self._now())
            findings = m.get_findings(findingIds=ids).get("findings", [])
            pii = [f for f in findings if "SensitiveData" in (f.get("type") or "")]
            summary = ("SensitiveData 분류 finding %d건 — PII 존재 확인" % len(pii)
                       if pii else "Macie finding %d건(PII 유형 아님)" % len(findings))
            return ToolResult(tool, resource_id, summary, bool(pii),
                              {"types": [f.get("type") for f in findings]}, self._now())
        except self._ClientError as e:
            code = e.response["Error"]["Code"]
            return ToolResult(tool, resource_id,
                              "Macie 조회 불가(%s — 서비스 미활성/권한) — 이 증거는 생략" % code,
                              False, {"error": code}, self._now())

    def _accessanalyzer_list_findings(self, tool: str, resource_id: str) -> ToolResult:
        """외부 접근 finding. analyzer 미생성/권한 부족이면 중립 결과."""
        native = resource_id.split(":", 2)[2]
        aa = self._client("accessanalyzer")
        try:
            analyzers = aa.list_analyzers(type="ACCOUNT").get("analyzers", [])
            if not analyzers:
                return ToolResult(tool, resource_id, "Access Analyzer 미생성 — 이 증거는 생략",
                                  False, {}, self._now())
            arn = analyzers[0]["arn"]
            fs = aa.list_findings(analyzerArn=arn, filter={
                "status": {"eq": ["ACTIVE"]}}).get("findings", [])
            hits = [f for f in fs if native in (f.get("resource") or "")]
            summary = ("외부 접근 ACTIVE finding %d건 — 외부 노출 확인" % len(hits)
                       if hits else "해당 리소스 외부 접근 finding 없음(ACTIVE %d건 중)" % len(fs))
            return ToolResult(tool, resource_id, summary, bool(hits),
                              {"active_total": len(fs), "matched": len(hits)}, self._now())
        except self._ClientError as e:
            code = e.response["Error"]["Code"]
            return ToolResult(tool, resource_id,
                              "Access Analyzer 조회 불가(%s) — 이 증거는 생략" % code,
                              False, {"error": code}, self._now())
