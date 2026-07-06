# CloudWatch Logs 구독 필터(CloudTrail ConsoleLogin 이벤트) -> SNS(팬아웃, teams_notifier가 Teams로 전달).
# CloudWatch 알람은 메트릭 임계값만 담아 "누가 로그인했는지"를 못 실어 나른다 — 그래서 알람이 아니라
# 로그 구독 필터로 CloudTrail 원본 레코드(userIdentity)를 그대로 받아 사용자명을 뽑아낸다.
# infra/monitoring 레이어 전용 — 다른 컴포넌트 패키지에 의존하지 않는 자립 파일(stdlib + boto3만).
import base64
import gzip
import json
import os

import boto3

_sns = boto3.client("sns")


def _extract_user(identity: dict) -> str:
    if identity.get("type") == "Root":
        return "root"
    name = identity.get("userName")
    if name:
        return name
    # SSO/federated·assumed-role 로그인은 arn 마지막 세그먼트가 실사용자를 가리킴.
    arn = identity.get("arn", "")
    return arn.rsplit("/", 1)[-1] if arn else "unknown"


def handler(event: dict, context) -> dict:
    payload = gzip.decompress(base64.b64decode(event["awslogs"]["data"]))
    data = json.loads(payload)

    sent = 0
    for log_event in data.get("logEvents", []):
        record = json.loads(log_event["message"])
        identity = record.get("userIdentity", {})
        user = _extract_user(identity)
        result = record.get("responseElements", {}).get("ConsoleLogin", "Unknown")
        ip = record.get("sourceIPAddress", "unknown")
        when = record.get("eventTime", "")
        emoji = "✅" if result == "Success" else "⚠️"
        body = f"사용자: **{user}**\n결과: {emoji} {result}\nIP: {ip}\n시각(UTC): {when}"
        message = {"kind": "custom", "title": "🔐 AWS 콘솔 로그인 감지", "body": body}
        _sns.publish(
            TopicArn=os.environ["SNS_TOPIC_ARN"],
            Subject="console-login",
            Message=json.dumps(message, ensure_ascii=False),
        )
        sent += 1

    return {"ok": True, "sent": sent}
