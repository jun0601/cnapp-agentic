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


def _region_code_from_arn(alarm_arn: str) -> str:
    """AlarmArn(arn:aws:cloudwatch:{region}:{account}:alarm:{name})에서 리전 코드 추출.
    alarm.Region은 사람이 읽는 이름("Asia Pacific (Seoul)")이라 콘솔 URL에 못 씀 — ARN에서 뽑는다."""
    parts = alarm_arn.split(":")
    return parts[3] if len(parts) > 3 else "ap-northeast-2"


def _log_group_link(region: str, function_name: str) -> str:
    """Lambda 함수의 CloudWatch Logs 로그그룹으로 바로 가는 콘솔 딥링크.
    로그그룹 이름의 '/'는 콘솔 해시라우팅에서 %2F를 다시 인코딩한 $252F로 표현해야 한다
    (CloudWatch Logs V2 콘솔 URL 스킴, AWS 표준 패턴)."""
    log_group = f"/aws/lambda/{function_name}".replace("/", "$252F")
    return f"https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#logsV2:log-groups/log-group/{log_group}"


def _alarm_link(region: str, alarm_name: str) -> str:
    """이 알람 자체의 CloudWatch 상세 페이지(히스토리·그래프)로 가는 링크."""
    from urllib.parse import quote
    return f"https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#alarmsV2:alarm/{quote(alarm_name)}"


def _diagnostic_links(alarm: dict) -> str:
    """알람 payload에서 진단에 바로 쓸 링크를 뽑아 HTML 조각으로 반환(없으면 빈 문자열).

    2026-07-10: "알림만 오고 원인은 매번 CloudWatch Logs를 손으로 찾아야 한다"는 지적 반영 —
    수신자가 클릭 한 번으로 알람 상세·(Lambda 알람이면) 관련 로그그룹까지 갈 수 있게 한다."""
    arn = alarm.get("AlarmArn", "")
    name = alarm.get("AlarmName", "")
    if not arn or not name:
        return ""
    region = _region_code_from_arn(arn)
    links = [f'<a href="{_alarm_link(region, name)}">알람 상세</a>']
    for dim in (alarm.get("Trigger", {}) or {}).get("Dimensions", []) or []:
        if dim.get("name") == "FunctionName" and dim.get("value"):
            links.append(f'<a href="{_log_group_link(region, dim["value"])}">Lambda 로그</a>')
            break
    return "<br><br>" + " · ".join(links)


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
    links = _diagnostic_links(alarm)
    return f"{emoji} <b>{name}</b> &rarr; <code>{state}</code><br><br>{reason}<br><br><i>region: {region}</i>{links}"


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
