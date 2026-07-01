"""member 서비스 — 회원 REST(+PII seeder) + shop 데모 포털 UI.

기능은 최소(target-app-design §7: 기능 최소, 결함 다양성 최대). 로컬에서 실제로 도는
유일한 서비스라, member가 'shop 데모 포털'로서 대표/서비스 소개 페이지도 서빙한다.
보안 결함(공개 버킷·과도 IRSA 등)은 앱 코드가 아니라 IaC(infra/target)에 심는다.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

from .models import Member, MemberCreate
from .seeder import generate_members, seed_to_s3
from . import web

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


app = FastAPI(title="member", version="0.2.0", lifespan=lifespan)


# ── UI (shop 데모 포털) ──────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def portal() -> str:
    return web.portal_html()


@app.get("/product", response_class=HTMLResponse)
def product_page() -> str:
    return web.product_html()


@app.get("/order", response_class=HTMLResponse)
def order_page() -> str:
    return web.order_html()


@app.get("/members", response_class=HTMLResponse)
def members_page() -> str:
    return web.members_html()


@app.get("/favicon.svg")
def favicon() -> Response:
    return Response(content=web.FAVICON_SVG, media_type="image/svg+xml")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


# ── API (JSON) — UI가 fetch. 실데이터/다른 서비스도 이걸 호출. ────────────────
@app.get("/api/members", response_model=List[Member])
def list_members(limit: int = 50) -> List[Member]:
    return _MEMBERS[:limit]


@app.get("/api/members/{member_id}", response_model=Member)
def get_member(member_id: int) -> Member:
    for m in _MEMBERS:
        if m.id == member_id:
            return m
    raise HTTPException(status_code=404, detail="member not found")


@app.post("/api/members", response_model=Member, status_code=201)
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
