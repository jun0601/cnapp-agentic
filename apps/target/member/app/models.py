"""회원 도메인 모델 (member 서비스).

member = 골든 시나리오의 'AWS 탈취 종착지'. 회원 PII를 S3에 보관하며,
공개 버킷 결함(infra/target)과 만나 데이터 탈취(f6·f7)로 이어진다.
※ 여기서 다루는 PII는 전부 faker 합성 데이터(실데이터 아님) — target-app-design §7.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Member(BaseModel):
    """회원 레코드. rrn(주민등록번호)은 Macie 탐지용 *합성 패턴*."""

    id: int
    name: str
    email: str
    phone: str
    # 주민등록번호 '형식'만 맞춘 합성값 — Macie의 KR-RRN 탐지를 발화시키기 위함(실번호 아님).
    rrn: str = Field(..., description="SYNTHETIC Korean RRN pattern (fake) — Macie trigger only")
    address: str


class MemberCreate(BaseModel):
    name: str
    email: str
    phone: str
    address: str
