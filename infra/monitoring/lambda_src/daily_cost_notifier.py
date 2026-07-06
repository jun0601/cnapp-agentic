# EventBridge(매일 09:00 KST) -> Cost Explorer(전날 비용 조회) -> Teams(전용 웹훅, cnapp-cost 채널).
# infra/monitoring 레이어 전용 — 다른 컴포넌트 패키지에 의존하지 않는 자립 파일(stdlib + boto3만).
import datetime
import json
import os
import urllib.request

import boto3

# Cost Explorer API 엔드포인트는 계정 리전과 무관하게 us-east-1 고정(AWS 제약) — Lambda 자체는 서울에서 실행.
_ce = boto3.client("ce", region_name="us-east-1")
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


def handler(event: dict, context) -> dict:
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    resp = _ce.get_cost_and_usage(
        TimePeriod={"Start": yesterday.isoformat(), "End": today.isoformat()},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        # RECORD_TYPE(Usage/Credit)로 쪼개지 않으면 프로모션 크레딧이 실사용을 100% 상쇄해
        # 순액이 늘 0에 가깝게 보여 "진짜 얼마 썼는지"를 알 수 없다(2026-07-06 실측:
        # 순액 -0.00000009 USD인데 실사용은 0.38 USD였음 — 크레딧 소진 시 대비 실사용을 노출).
        GroupBy=[{"Type": "DIMENSION", "Key": "RECORD_TYPE"}],
    )
    results = resp.get("ResultsByTime", [])
    groups = results[0].get("Groups", []) if results else []

    usage = 0.0
    credit = 0.0
    currency = "USD"
    for g in groups:
        record_type = g["Keys"][0]
        metric = g["Metrics"]["UnblendedCost"]
        currency = metric.get("Unit", currency)
        amount = float(metric.get("Amount", "0"))
        if record_type == "Usage":
            usage += amount
        elif record_type == "Credit":
            credit += amount
    net = usage + credit

    # 메시지 필드는 마크다운이 아니라 HTML 리치텍스트라 <b>/<br>로 서식을 넣어야 실제로 렌더링된다
    # (2026-07-06 확인 — **볼드**를 그대로 보내면 별표 문자 그대로 나옴).
    text = (
        f"<b>💰 어제 AWS 사용 비용</b><br><br>"
        f"{yesterday.isoformat()} 사용 비용<br>"
        f"- 실사용(크레딧 적용 전): <b>{usage:.4f} {currency}</b><br>"
        f"- 크레딧 상쇄: {credit:.4f} {currency}<br>"
        f"- 순액(실청구): <b>{net:.4f} {currency}</b>"
    )
    _post_to_teams(text)
    return {"ok": True, "date": yesterday.isoformat(), "usage": usage, "credit": credit, "net": net}
