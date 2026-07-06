# product 서비스 = AWS retail-store-sample-app의 catalog 서비스 fork.
# 기능은 그대로 두고, "취약 이미지" 결함(f1)만 심는다.
#
# ── 의도적 결함 f1 (INTERNAL-VULN-KEV-001) ──────────────────────────────────
# 일부러 KEV 등재 CVE가 있는 '오래된 베이스 이미지'로 재빌드한다.
# Trivy(빌드 게이트)·Inspector(ECR)가 이 이미지를 스캔해 KEV finding을 발화.
# ⚠️ 데모 전용. 실제 서비스에 쓰지 말 것. 결함 토글은 infra/target 배포 파이프라인에서.
FROM public.ecr.aws/docker/library/amazonlinux:2.0.20230307.0
# ↑ 의도적으로 낡은 태그(패치 미적용) — KEV 포함 CVE 다수. 최신은 amazonlinux:2023.

# retail-store catalog 바이너리/런타임을 여기에 복사(fork 소스는 upstream에서).
# 데모 스캐폴드에서는 이미지 결함 시연이 목적이라 앱 바이너리 COPY는 배포 시 연결.
WORKDIR /app
# COPY --from=upstream /catalog /app/catalog   # (배포 파이프라인에서 연결)

EXPOSE 8080
# placeholder — 실제 catalog 실행으로 교체.
# WARNING: exec-form(JSON 배열) 실행 지시 뒤에 같은 줄로 인라인 주석(# ...)을 붙이면 Docker가
#    그 줄을 JSON으로 파싱하다 실패해 shell-form으로 폴백 -> "/bin/sh -c '[sleep, infinity]'"로
#    실행돼 "/bin/sh: [sleep,: command not found"로 크래시(2026-07-06 라이브 실측). 주석은 윗줄에.
CMD ["sleep", "infinity"]
