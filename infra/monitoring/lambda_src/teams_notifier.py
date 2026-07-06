# SNS(CloudWatch Alarms 팬아웃) -> Teams(Power Automate webhook) 어댑터.
# infra/monitoring 레이어 전용 — 다른 컴포넌트 패키지에 의존하지 않는 자립 파일(stdlib + boto3만).
# boto3는 Lambda 런타임에 기본 포함이라 별도 레이어/의존성 불필요.
import json
import os
import urllib.request

import boto3

_secrets = boto3.client("secretsmanager")
_webhook_url_cache = None


def _get_webhook_url() -> str:
    global _webhook_url_cache
    if _webhook_url_cache is None:
        secret_id = os.environ["WEBHOOK_SECRET_ARN"]
        resp = _secrets.get_secret_value(SecretId=secret_id)
        _webhook_url_cache = resp["SecretString"]
    return _webhook_url_cache


def _to_teams_card(alarm: dict) -> dict:
    if alarm.get("kind") == "custom":
        # daily_cost_notifier·login_notifier처럼 CloudWatch 알람이 아닌 능동 발행 메시지.
        title = alarm.get("title", "알림")
        body = alarm.get("body", "")
        return {"text": f"**{title}**\n\n{body}"}
    name = alarm.get("AlarmName", "unknown-alarm")
    state = alarm.get("NewStateValue", "")
    reason = alarm.get("NewStateReason", "")
    region = alarm.get("Region", "")
    emoji = "🔴" if state == "ALARM" else ("🟢" if state == "OK" else "⚪")
    text = f"{emoji} **{name}** → `{state}`\n\n{reason}\n\n_region: {region}_"
    # Power Automate "Teams에 웹훅 요청 게시" 트리거는 최소 {"text": "..."} 형태를 그대로 카드 본문에 반영한다.
    return {"text": text}


def handler(event: dict, context) -> dict:
    sent = 0
    for record in event.get("Records", []):
        raw = record.get("Sns", {}).get("Message", "{}")
        try:
            alarm = json.loads(raw)
        except json.JSONDecodeError:
            # CloudWatch Alarm이 아닌 임의 SNS 메시지(수동 테스트 등) 대비 — 원문 그대로 감싸서 보냄.
            alarm = {"AlarmName": record.get("Sns", {}).get("Subject", "alert"), "NewStateReason": raw}

        body = json.dumps(_to_teams_card(alarm)).encode("utf-8")
        req = urllib.request.Request(
            _get_webhook_url(),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        sent += 1

    return {"ok": True, "sent": sent}
