"""member 서비스 — 회원 가입/조회 REST (FastAPI).

기능은 최소(target-app-design §7: 기능 최소, 결함 다양성 최대). 목적은
① 골든 시나리오용 합성 PII를 S3에 채우고 ② 회원 서비스가 '실재'하는 것처럼 보이게 하는 것.
보안 결함(공개 버킷·과도 IRSA 등)은 앱 코드가 아니라 IaC(infra/target)에 심는다.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .models import Member, MemberCreate
from .seeder import generate_members, seed_to_s3
from .web import INDEX_HTML

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("member")

# 인메모리 회원 저장소(데모용). 실제 PII 원본은 S3(seeder)에 있다.
_MEMBERS: List[Member] = []


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 기동 시: S3에 합성 PII 적재(버킷 설정 시) + 인메모리 목록 채우기
    try:
        seeded = seed_to_s3()
        log.info("startup seeding done (%d records to S3)", seeded)
    except Exception as exc:  # noqa: BLE001 — 데모: seeding 실패해도 서비스는 기동
        log.warning("PII seeding skipped/failed: %s", exc)
    _MEMBERS.extend(generate_members(int(os.getenv("MEMBER_INMEM_COUNT", "20"))))
    yield
    _MEMBERS.clear()


app = FastAPI(title="member", version="0.1.0", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    # §7 '최소 스킨' — 회원 목록 + 가입 폼(취약점 배너 포함). 데이터는 가짜.
    return INDEX_HTML


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/members", response_model=List[Member])
def list_members(limit: int = 50) -> List[Member]:
    return _MEMBERS[:limit]


@app.get("/members/{member_id}", response_model=Member)
def get_member(member_id: int) -> Member:
    for m in _MEMBERS:
        if m.id == member_id:
            return m
    raise HTTPException(status_code=404, detail="member not found")


@app.post("/members", response_model=Member, status_code=201)
def create_member(body: MemberCreate) -> Member:
    from .seeder import _synthetic_rrn  # 합성 rrn 부여(데모)

    new = Member(
        id=(max((m.id for m in _MEMBERS), default=0) + 1),
        name=body.name,
        email=body.email,
        phone=body.phone,
        rrn=_synthetic_rrn(),
        address=body.address,
    )
    _MEMBERS.append(new)
    return new
