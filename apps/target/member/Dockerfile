# member 서비스 — Python/FastAPI. 비루트·슬림 베이스(이 이미지 자체는 '깨끗'하게).
# ※ member의 보안 결함은 앱 이미지가 아니라 IaC(공개 S3·데이터)에 있다.
#   취약 이미지 결함(f1)은 product 서비스가 담당(별도 KEV 베이스).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 비루트 실행
RUN useradd -m -u 10001 appuser
USER appuser

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
