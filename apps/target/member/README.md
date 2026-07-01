# member 서비스 (타깃 앱 — 신규 작성)

회원 가입/조회 REST + **PII seeder**. 골든 시나리오의 **AWS 데이터 탈취 종착지**.
스택 = **Python / FastAPI**(target-app-design §7 피드백 결정 — 경량 REST + faker + boto3).

> ⚠️ 여기서 다루는 PII는 전부 **faker 합성 데이터**(실제 개인정보 아님). `rrn`은 주민번호 *형식*만 맞춘 가짜로, **Macie의 KR-RRN 탐지를 발화**시키기 위한 미끼다(§7).

## 역할 (골든 시나리오)

- 기동 시 합성 회원 PII를 **S3(`member-pii-prod`)에 적재**(`app/seeder.py`).
- 그 버킷을 **공개**로 만드는 결함은 앱이 아니라 **IaC(`infra/target`)**에 있다 → Macie가 PII 탐지(f7) + Security Hub가 공개 버킷 탐지(f6).
- 즉 앱 이미지/워크로드는 **깨끗**(비루트·최소권한), **결함은 인프라·데이터에** 둔다.

## 구조

```
member/
├── app/
│   ├── main.py      FastAPI — GET/POST /members, /health, 기동 시 seeding
│   ├── seeder.py    합성 PII 생성 + S3 적재(idempotent)
│   └── models.py    Member(pydantic)
├── k8s/             Deployment(비루트·IRSA) · Service
├── Dockerfile       python:3.12-slim, 비루트
└── requirements.txt
```

## 로컬 실행

```bash
pip install -r requirements.txt
# S3 없이(로컬): seeding 스킵되고 인메모리 회원만
uvicorn app.main:app --reload --port 8080
# S3 적재까지: 자격증명 + 버킷 지정
export MEMBER_PII_BUCKET=member-pii-prod MEMBER_PII_COUNT=200 AWS_REGION=ap-northeast-2
uvicorn app.main:app --port 8080
```

## 환경변수

| 변수 | 기본 | 설명 |
|---|---|---|
| `MEMBER_PII_BUCKET` | (없음) | 대상 S3 버킷. 미설정 시 seeding 스킵 |
| `MEMBER_PII_COUNT` | 200 | S3에 적재할 합성 PII 건수 |
| `MEMBER_INMEM_COUNT` | 20 | 인메모리 회원 목록 건수(REST용) |
| `AWS_REGION` | ap-northeast-2 | |

## API

| 메서드·경로 | 설명 |
|---|---|
| `GET /health` | 헬스체크 |
| `GET /members?limit=` | 회원 목록(합성) |
| `GET /members/{id}` | 단건 |
| `POST /members` | 회원 생성(합성 rrn 부여) |
