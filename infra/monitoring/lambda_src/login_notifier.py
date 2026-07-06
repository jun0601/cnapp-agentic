# CloudWatch Logs 구독 필터(CloudTrail ConsoleLogin 이벤트) -> Teams(전용 웹훅, cnapp-login 채널).
# CloudWatch 알람은 메트릭 임계값만 담아 "누가 로그인했는지"를 못 실어 나른다 — 그래서 알람이 아니라
# 로그 구독 필터로 CloudTrail 원본 레코드(userIdentity)를 그대로 받아 사용자명을 뽑아낸다.
# infra/monitoring 레이어 전용 — 다른 컴포넌트 패키지에 의존하지 않는 자립 파일(stdlib + boto3만).
import base64
import datetime
import gzip
import json
import os
import urllib.request

import boto3

_KST = datetime.timezone(datetime.timedelta(hours=9))

_secrets = boto3.client("secretsmanager")
_webhook_url_cache = None


def _get_webhook_url() -> str:
    global _webhook_url_cache
    if _webhook_url_cache is None:
        resp = _secrets.get_secret_value(SecretId=os.environ["WEBHOOK_SECRET_ARN"])
        _webhook_url_cache = resp["SecretString"]
    return _webhook_url_cache


def _post_to_teams(text: str) -> None:
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        _get_webhook_url(),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def _extract_user(identity: dict) -> str:
    if identity.get("type") == "Root":
        return "root"
    name = identity.get("userName")
    if name:
        return name
    # SSO/federated·assumed-role 로그인은 arn 마지막 세그먼트가 실사용자를 가리킴.
    arn = identity.get("arn", "")
    return arn.rsplit("/", 1)[-1] if arn else "unknown"


def _to_kst(event_time_utc: str) -> str:
    # CloudTrail eventTime은 항상 UTC "%Y-%m-%dT%H:%M:%SZ" 형식.
    try:
        dt = datetime.datetime.strptime(event_time_utc, "%Y-%m-%dT%H:%M:%SZ")
        dt = dt.replace(tzinfo=datetime.timezone.utc).astimezone(_KST)
        return dt.strftime("%Y-%m-%d %H:%M:%S") + " KST"
    except ValueError:
        return event_time_utc  # 예상 밖 형식이면 원본 그대로(알림 자체는 계속 감)


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
        when = _to_kst(record.get("eventTime", ""))
        emoji = "✅" if result == "Success" else "⚠️"
        text = f"**🔐 AWS 콘솔 로그인 감지**\n\n사용자: **{user}**\n결과: {emoji} {result}\nIP: {ip}\n시각(KST): {when}"
        _post_to_teams(text)
        sent += 1

    return {"ok": True, "sent": sent}
