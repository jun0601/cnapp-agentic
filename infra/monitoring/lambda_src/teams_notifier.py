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


def _to_teams_text(alarm: dict) -> str:
    # Power Automate "채팅 또는 채널에서 메시지 게시" 액션의 메시지 필드는 마크다운이 아니라
    # HTML 리치텍스트 에디터라서, **볼드**·개행(\n)을 그대로 보내면 문자 그대로("**"가 안 없어짐)
    # 나온다 — <b>·<br>로 직접 HTML 태그를 써야 실제로 굵게/줄바꿈이 렌더링된다(2026-07-06 확인).
    if alarm.get("kind") == "custom":
        # daily_cost_notifier·login_notifier처럼 CloudWatch 알람이 아닌 능동 발행 메시지.
        title = alarm.get("title", "알림")
        body = alarm.get("body", "").replace("\n", "<br>")
        return f"<b>{title}</b><br><br>{body}"
    name = alarm.get("AlarmName", "unknown-alarm")
    state = alarm.get("NewStateValue", "")
    reason = alarm.get("NewStateReason", "")
    region = alarm.get("Region", "")
    emoji = "🔴" if state == "ALARM" else ("🟢" if state == "OK" else "⚪")
    return f"{emoji} <b>{name}</b> &rarr; <code>{state}</code><br><br>{reason}<br><br><i>region: {region}</i>"


def _to_teams_payload(alarm: dict) -> dict:
    # 이 프로젝트의 Power Automate 흐름("cnapp-alerts에 웹후크 경고 보내기")은 Teams 전용
    # 웹후크 트리거(Teams 웹후크 요청이 수신된 경우) + "채팅 또는 채널에서 메시지 게시"
    # (평문, triggerBody()?['text'] 매핑) 조합 — 흐름 템플릿 기본 "Post card" 액션은
    # 본문을 Adaptive Card로 직접 파싱하려 해서 우리 payload와 안 맞아 삭제하고 교체했다
    # (2026-07-06 실측, infra/monitoring/README.md §17 참고). 그래서 여기선 평문만 보내면 된다.
    return {"text": _to_teams_text(alarm)}


def handler(event: dict, context) -> dict:
    sent = 0
    for record in event.get("Records", []):
        raw = record.get("Sns", {}).get("Message", "{}")
        try:
            alarm = json.loads(raw)
        except json.JSONDecodeError:
            # CloudWatch Alarm이 아닌 임의 SNS 메시지(수동 테스트 등) 대비 — 원문 그대로 감싸서 보냄.
            alarm = {"AlarmName": record.get("Sns", {}).get("Subject", "alert"), "NewStateReason": raw}

        body = json.dumps(_to_teams_payload(alarm)).encode("utf-8")
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
