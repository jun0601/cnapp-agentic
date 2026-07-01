"""PII seeder — 기동 시 합성 회원 PII를 생성해 S3(member-pii-prod)에 적재.

이 데이터가 있어야 Macie가 'SensitiveData:PII'를 탐지하고 골든 시나리오의
데이터 탈취(f7, INTERNAL-DATA-PII-EXPOSED-001)가 발화한다. 버킷의 '공개' 결함은
IaC(infra/target)에 있고, 여기서는 '민감해 보이는' 데이터를 채우는 역할만 한다.

⚠️ 생성되는 값은 전부 faker 합성(실제 개인정보 아님). rrn은 형식만 맞춘 가짜.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import random
from typing import List

import boto3
from botocore.exceptions import ClientError
from faker import Faker

from .models import Member

log = logging.getLogger("member.seeder")
fake = Faker("ko_KR")


def _synthetic_rrn() -> str:
    """주민등록번호 '형식'의 합성값(YYMMDD-GXXXXXX). 실번호 아님 — Macie 패턴 발화용."""
    yy = random.randint(0, 99)
    mm = random.randint(1, 12)
    dd = random.randint(1, 28)
    gender = random.randint(1, 4)
    tail = random.randint(0, 999999)
    return f"{yy:02d}{mm:02d}{dd:02d}-{gender}{tail:06d}"


def generate_members(n: int) -> List[Member]:
    members: List[Member] = []
    for i in range(1, n + 1):
        members.append(
            Member(
                id=i,
                name=fake.name(),
                email=fake.email(),
                phone=fake.phone_number(),
                rrn=_synthetic_rrn(),
                address=fake.address().replace("\n", " "),
            )
        )
    return members


def _to_csv(members: List[Member]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["id", "name", "email", "phone", "rrn", "address"])
    writer.writeheader()
    for m in members:
        writer.writerow(m.model_dump())
    return buf.getvalue()


def seed_to_s3() -> int:
    """S3에 합성 PII 적재. 이미 있으면 건너뜀(idempotent). 적재 건수 반환.

    환경변수:
      MEMBER_PII_BUCKET  대상 버킷(예: member-pii-prod) — 없으면 seeding 스킵
      MEMBER_PII_COUNT   생성 건수(기본 200)
      AWS_REGION         리전(기본 ap-northeast-2)
    """
    bucket = os.getenv("MEMBER_PII_BUCKET")
    if not bucket:
        log.warning("MEMBER_PII_BUCKET 미설정 — PII seeding 스킵(로컬 개발 모드)")
        return 0

    count = int(os.getenv("MEMBER_PII_COUNT", "200"))
    region = os.getenv("AWS_REGION", "ap-northeast-2")
    key = "members/pii_export.csv"

    s3 = boto3.client("s3", region_name=region)

    # idempotent — 이미 적재됐으면 재생성 안 함
    try:
        s3.head_object(Bucket=bucket, Key=key)
        log.info("PII already seeded at s3://%s/%s — skip", bucket, key)
        return 0
    except ClientError as exc:
        # 404(Not Found)면 아직 없음 → 적재 진행. 그 외 오류는 다시 던진다.
        if exc.response.get("Error", {}).get("Code") not in ("404", "NoSuchKey", "NotFound"):
            raise

    members = generate_members(count)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=_to_csv(members).encode("utf-8"),
        ContentType="text/csv",
    )
    # 요약 메타(민감정보 없음)도 하나 남겨 데모 가독성↑
    s3.put_object(
        Bucket=bucket,
        Key="members/_seed_meta.json",
        Body=json.dumps({"count": count, "synthetic": True, "note": "faker-generated, not real PII"}).encode(),
        ContentType="application/json",
    )
    log.info("seeded %d synthetic PII records → s3://%s/%s", count, bucket, key)
    return count
