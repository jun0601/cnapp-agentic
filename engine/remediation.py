"""조치 실행기(HITL) — Step Functions ApplyFix Task의 Lambda 진입점. ★유일한 '쓰기' 경로.

read-only 조사(evidence)와 분리된 격상 역할에서만 동작(§17 최소권한 분리). 흐름:
  콘솔 approver 승인 → console-backend가 StartExecution(입력=아래 event)
    → SFn ValidateApproval → ApplyFix(이 핸들러) → RecordAudit

MVP 카탈로그 3종(project-draft §24): S3 public block · open SG(0.0.0.0) 제거 · IAM 최소권한.
각 액션은 dry_run=True(계획만) / False(실제 변경). 성공 시:
  ① 감사 기록을 S3 Object Lock 버킷(AUDIT_BUCKET)에 불변 저장(§17)
  ② RDS 상태 갱신 — remediation_requests=applied · findings=remediated (console-app-design §6.1 수정→소멸 루프)

Lambda 설정(infra/engine):
  handler = "engine.remediation.handler"
  role    = 격상 정책(s3/ec2/iam 변경 + audit PutObject + RDS secret) — 격리된 역할
  env     = AUDIT_BUCKET · DB_HOST · DB_SECRET_ARN  · VPC(RDS 접근)
⚠️ 실 변경 API 호출 코드 — apply 세션에서만 라이브 검증(dry_run으로 먼저 계획 확인 권장).

event 예:
  {"remediation_id":"...","finding_id":"...","approver":"approver@...","action":"s3_block_public",
   "target":{"bucket":"cnapp-agentic-member-pii-..."},"dry_run":false}
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

_ACTIONS = {
    "s3_block_public", "sg_remove_open_ingress", "iam_least_privilege",
    "s3_enable_encryption", "ecr_enable_scan_on_push",  # 2026-07-08 추가
    "s3_enable_logging",  # 2026-07-22 추가(드리프트 X — INTERNAL-S3-LOGGING-DISABLED-001 조치)
}


def handler(event: dict, context=None) -> dict:
    action = event.get("action")
    if action not in _ACTIONS:
        raise ValueError("unknown remediation action: %s (허용=%s)" % (action, sorted(_ACTIONS)))
    dry_run = bool(event.get("dry_run", False))
    target = event.get("target") or {}
    region = os.environ.get("AWS_REGION", "ap-northeast-2")

    result = _dispatch(action, target, dry_run, region)

    record = {
        "remediation_id": event.get("remediation_id"),
        "finding_id": event.get("finding_id"),
        "approver": event.get("approver"),
        "action": action,
        "dry_run": dry_run,
        "result": result,
        "ts": _now(),
    }
    # 실제 변경이 적용된 경우에만 불변 감사 기록 + RDS 상태 갱신(수정→소멸 루프)
    if not dry_run and result.get("applied"):
        _write_audit(record, region)
        _mark_remediated(event.get("remediation_id"), event.get("finding_id"),
                         event.get("approver"), region)
        _retrigger_correlation(region)  # finding=remediated 반영해 attack_paths 재계산(경로 소멸)
    return record


# ── 액션 디스패치 ──────────────────────────────────────────────────────
def _dispatch(action: str, target: dict, dry_run: bool, region: str) -> dict:
    if action == "s3_block_public":
        return _s3_block_public(target["bucket"], dry_run, region)
    if action == "sg_remove_open_ingress":
        return _sg_remove_open_ingress(target["security_group_id"], dry_run, region)
    if action == "iam_least_privilege":
        return _iam_least_privilege(target["role_name"], target["policy_name"],
                                    target.get("policy_document"), dry_run, region)
    if action == "s3_enable_encryption":
        return _s3_enable_encryption(target["bucket"], dry_run, region)
    if action == "ecr_enable_scan_on_push":
        return _ecr_enable_scan_on_push(target["repository_name"], dry_run, region)
    if action == "s3_enable_logging":
        return _s3_enable_logging(target["bucket"], target.get("log_bucket"), dry_run, region)
    raise ValueError(action)  # _ACTIONS 게이트를 통과했으므로 도달 불가


def _s3_block_public(bucket: str, dry_run: bool, region: str) -> dict:
    """공개 S3 버킷 → Block Public Access 4종 전부 활성(f6 되돌림)."""
    plan = {"api": "s3:PutBucketPublicAccessBlock", "bucket": bucket,
            "change": "BlockPublicAcls/IgnorePublicAcls/BlockPublicPolicy/RestrictPublicBuckets = true"}
    if dry_run:
        return {"applied": False, "plan": plan}
    import boto3
    boto3.client("s3", region_name=region).put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True,
            "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
        },
    )
    return {"applied": True, "plan": plan}


def _sg_remove_open_ingress(sg_id: str, dry_run: bool, region: str) -> dict:
    """보안그룹에서 0.0.0.0/0(및 ::/0) 인바운드 규칙만 골라 제거(f3 되돌림)."""
    import boto3
    ec2 = boto3.client("ec2", region_name=region)
    sg = ec2.describe_security_groups(GroupIds=[sg_id])["SecurityGroups"][0]

    open_perms = []
    for perm in sg.get("IpPermissions", []):
        v4 = [r for r in perm.get("IpRanges", []) if r.get("CidrIp") == "0.0.0.0/0"]
        v6 = [r for r in perm.get("Ipv6Ranges", []) if r.get("CidrIpv6") == "::/0"]
        if not (v4 or v6):
            continue
        p = {k: perm[k] for k in ("IpProtocol", "FromPort", "ToPort") if k in perm}
        if v4:
            p["IpRanges"] = v4
        if v6:
            p["Ipv6Ranges"] = v6
        open_perms.append(p)

    plan = {"api": "ec2:RevokeSecurityGroupIngress", "security_group_id": sg_id,
            "revoke_count": len(open_perms), "rules": open_perms}
    if dry_run or not open_perms:
        return {"applied": False, "plan": plan}  # 열린 규칙 없으면 no-op
    ec2.revoke_security_group_ingress(GroupId=sg_id, IpPermissions=open_perms)
    return {"applied": True, "plan": plan}


def _iam_least_privilege(role_name: str, policy_name: str,
                         policy_document, dry_run: bool, region: str) -> dict:
    """과도권한 인라인 정책을 최소권한 문서로 교체(f4 되돌림). 현재→제안 diff 포함."""
    import boto3
    iam = boto3.client("iam", region_name=region)
    try:
        current = iam.get_role_policy(RoleName=role_name, PolicyName=policy_name)["PolicyDocument"]
    except Exception:  # noqa: BLE001 — 정책 없거나 조회 실패 시 diff의 current=None
        current = None

    plan = {"api": "iam:PutRolePolicy", "role": role_name, "policy": policy_name,
            "current": current, "proposed": policy_document}
    if dry_run or not policy_document:
        return {"applied": False, "plan": plan}  # 제안 문서 없으면 diff만(적용 안 함)
    iam.put_role_policy(RoleName=role_name, PolicyName=policy_name,
                        PolicyDocument=json.dumps(policy_document))
    return {"applied": True, "plan": plan}


def _s3_enable_encryption(bucket: str, dry_run: bool, region: str) -> dict:
    """S3 버킷 서버측 암호화(SSE-S3/AES256) 활성화(INTERNAL-S3-NOENCRYPT-001 되돌림, 2026-07-08).

    KMS(SSE-KMS)가 아니라 AES256을 쓰는 이유: 추가 키 관리·비용 없이 즉시 적용 가능한
    최소조치(무료 티어 규율, cost-strategy.md와 정합) — 더 강한 암호화가 필요하면 후속으로 격상.
    """
    plan = {"api": "s3:PutBucketEncryption", "bucket": bucket,
            "change": "ServerSideEncryptionConfiguration = SSE-S3(AES256)"}
    if dry_run:
        return {"applied": False, "plan": plan}
    import boto3
    boto3.client("s3", region_name=region).put_bucket_encryption(
        Bucket=bucket,
        ServerSideEncryptionConfiguration={
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        },
    )
    return {"applied": True, "plan": plan}


def _ecr_enable_scan_on_push(repository_name: str, dry_run: bool, region: str) -> dict:
    """ECR 리포지토리 scan-on-push(이미지 취약점 자동 스캔) 활성화
    (INTERNAL-ECR-SCAN-DISABLED-001 되돌림, 2026-07-08)."""
    plan = {"api": "ecr:PutImageScanningConfiguration", "repository": repository_name,
            "change": "imageScanningConfiguration.scanOnPush = true"}
    if dry_run:
        return {"applied": False, "plan": plan}
    import boto3
    boto3.client("ecr", region_name=region).put_image_scanning_configuration(
        repositoryName=repository_name,
        imageScanningConfiguration={"scanOnPush": True},
    )
    return {"applied": True, "plan": plan}


def _s3_enable_logging(bucket: str, log_bucket, dry_run: bool, region: str) -> dict:
    """S3 서버 액세스 로깅 활성화(INTERNAL-S3-LOGGING-DISABLED-001 되돌림, 2026-07-22).
    드리프트 X — terraform이 이 버킷의 logging 속성을 관리하지 않는다.
    log_bucket 미지정 시 자기 자신을 대상으로(데모 단순화 — 실서비스는 전용 로그 버킷)."""
    dest = log_bucket or bucket
    plan = {"api": "s3:PutBucketLogging", "bucket": bucket,
            "change": "LoggingEnabled.TargetBucket = %s" % dest}
    if dry_run:
        return {"applied": False, "plan": plan}
    import boto3
    boto3.client("s3", region_name=region).put_bucket_logging(
        Bucket=bucket,
        BucketLoggingStatus={"LoggingEnabled": {"TargetBucket": dest, "TargetPrefix": "s3-access/%s/" % bucket}},
    )
    return {"applied": True, "plan": plan}



# ── 감사(불변) + RDS 상태 갱신 ─────────────────────────────────────────
def _write_audit(record: dict, region: str) -> None:
    """S3 Object Lock 버킷에 감사 레코드를 불변 저장(§17 — 조치 후 사후 변조 불가).

    이 함수가 호출되는 시점엔 이미 실 변경(dry_run=False, applied=True)이 끝난 뒤라,
    AUDIT_BUCKET 미설정으로 조용히 skip하면 "실 클라우드 변경은 있었는데 불변 감사
    기록이 없는" 상태가 되어 §17 보장을 깬다 — 조용히 넘기지 않고 예외로 실패시켜
    Lambda 에러(→ infra/monitoring의 lambda_errors 알람)로 드러나게 한다.
    """
    bucket = os.environ.get("AUDIT_BUCKET")
    if not bucket:
        raise RuntimeError(
            "AUDIT_BUCKET 미설정 — 실 변경(%s)이 적용됐는데 불변 감사 기록을 못 남김(§17 위반)"
            % record.get("action")
        )
    import boto3
    key = "remediation/%s-%s.json" % (record["ts"].replace(":", ""),
                                      record.get("remediation_id") or "na")
    boto3.client("s3", region_name=region).put_object(
        Bucket=bucket, Key=key,
        Body=json.dumps(record, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )


def _mark_remediated(remediation_id, finding_id, approver, region: str) -> None:
    """수정→소멸 루프(console §6.1): remediation_requests=applied · findings=remediated."""
    if not (os.environ.get("DB_HOST") and os.environ.get("DB_SECRET_ARN")):
        return  # DB 미배선(로컬/무 VPC)면 조용히 skip
    conn = _connect(region)
    try:
        with conn, conn.cursor() as cur:
            if remediation_id:
                cur.execute(
                    "UPDATE remediation_requests SET status='applied', approver=%s, "
                    "updated_at=now() WHERE id=%s;",
                    (approver, remediation_id),
                )
            if finding_id:
                cur.execute("UPDATE findings SET status='remediated' WHERE finding_id=%s;",
                            (finding_id,))
    finally:
        conn.close()


def _retrigger_correlation(region: str) -> None:
    """조치로 finding이 remediated된 뒤 correlation Lambda를 비동기 재실행 → attack_paths 재계산.

    '수정→소멸 루프'(console §6.1)를 개별 finding뿐 아니라 **공격 경로 리스트**에도 반영한다:
    조치로 finding이 open에서 빠지면, 그 finding에 의존하던 attack-path가 correlation 재계산에서
    미발화 → 콘솔 경로 리스트에서 사라진다("공개버킷 차단 → 그 버킷을 쓰던 경로들이 동시에 닫힘").

    - InvocationType=Event(비동기) — 조치 응답을 안 막고 fire-and-forget.
    - CORRELATION_FUNCTION 미설정(로컬/무 배선)이면 조용히 skip.
    - 재트리거 실패가 조치 자체를 실패시키면 안 되므로 광범위 except로 삼킴(조치는 이미 완료됨).
    """
    fn = os.environ.get("CORRELATION_FUNCTION")
    if not fn:
        return
    try:
        import boto3
        boto3.client("lambda", region_name=region).invoke(
            FunctionName=fn, InvocationType="Event", Payload=b"{}",
        )
    except Exception:  # noqa: BLE001 — 관측/재계산 실패가 본 조치를 막지 않게
        pass


def _connect(region: str):
    import boto3
    import psycopg2
    sm = boto3.client("secretsmanager", region_name=region)
    sec = json.loads(sm.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"])
    return psycopg2.connect(
        host=os.environ["DB_HOST"], port=5432,
        dbname=sec.get("dbname", "cnapp"), user=sec["username"], password=sec["password"],
        connect_timeout=5,
        sslmode="require",  # in-transit TLS 강제(#2). 기본 'prefer'는 TLS 선택적 → require로 필수화(CA 핀닝 verify-full은 후속).
    )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
