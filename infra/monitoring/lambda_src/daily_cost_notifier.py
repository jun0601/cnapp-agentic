# EventBridge(매일 09:00 KST) -> Cost Explorer(전날 비용 조회) -> SNS(팬아웃, teams_notifier가 Teams로 전달).
# infra/monitoring 레이어 전용 — 다른 컴포넌트 패키지에 의존하지 않는 자립 파일(stdlib + boto3만).
import datetime
import json
import os

import boto3

# Cost Explorer API 엔드포인트는 계정 리전과 무관하게 us-east-1 고정(AWS 제약) — Lambda 자체는 서울에서 실행.
_ce = boto3.client("ce", region_name="us-east-1")
_sns = boto3.client("sns")


def handler(event: dict, context) -> dict:
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    resp = _ce.get_cost_and_usage(
        TimePeriod={"Start": yesterday.isoformat(), "End": today.isoformat()},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
    )
    results = resp.get("ResultsByTime", [])
    total = results[0]["Total"]["UnblendedCost"] if results else {"Amount": "0", "Unit": "USD"}
    amount = float(total.get("Amount", "0"))
    currency = total.get("Unit", "USD")

    body = f"{yesterday.isoformat()} 사용 비용: **{amount:.4f} {currency}**"
    message = {"kind": "custom", "title": "💰 어제 AWS 사용 비용", "body": body}
    _sns.publish(
        TopicArn=os.environ["SNS_TOPIC_ARN"],
        Subject="daily-cost-report",
        Message=json.dumps(message, ensure_ascii=False),
    )
    return {"ok": True, "date": yesterday.isoformat(), "amount": amount, "currency": currency}
