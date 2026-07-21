# infra/slice — 엔진 실 tool-use vertical slice 표적

> 엔진의 유일한 차별점("LLM이 스스로 read-only API 호출")을 **최소 크레딧(<$1)**으로 실제 증명하기
> 위한 최소 표적. 공개 S3 버킷 1개 + 가짜 PII 객체 1개만 만든다. `infra/shared`와 무관한 독립 스택.

## 무엇을 만드나
- 공개 S3 버킷 1개(`cnapp-slice-member-pii-<rand>`) — public access block 해제 + 공개 읽기 정책
- 가짜 PII 객체 1개(`members/fake-pii.json`, faker 합성값 — 실제 개인정보 아님)
- **EKS·RDS·NAT·Macie 없음** → 스토리지·요청 몇 센트 수준

## 어떻게 쓰나 (apply는 준형과 함께 · 테스트 후 즉시 destroy)
```bash
cd infra/slice
terraform init
terraform apply -var 'profile=cnapp'          # 공개 버킷 1개 생성
terraform output resource_id                   # → aws:s3_bucket:cnapp-slice-member-pii-xxxx

# 엔진 실 tool-use 테스트: 이 resource_id를 RealToolExecutor로 조사
#   (실 LLM 플래너는 구현·검증 완료 — engine/evidence/bedrock_planner.py)

terraform destroy -var 'profile=cnapp'         # ★ 테스트 끝나면 즉시
```

## ⚠️ apply 시 확인 (준형과)
- **계정 레벨 S3 Block Public Access**가 켜져 있으면 공개 정책 apply가 거부될 수 있음
  → `-var 'enable_public_policy=false'`로 두면 PAB-off 신호만으로도 tool-use 데모 가능
  (RealToolExecutor는 `GetPublicAccessBlock`에서 '차단 없음'을 관측).
- **RealToolExecutor의 신원**(로컬 `cnapp` 프로파일 또는 전용 역할)이 `s3:GetBucketPolicy`·
  `s3:GetBucketPublicAccessBlock` 권한을 가져야 함(계약④ evidence-allowlist 범위).
- **Bedrock 모델**: ✅ 확정 — `global.anthropic.claude-haiku-4-5-20251001-v1:0`(서울 global inference profile). shared의 `bedrock_invoke` 정책이 이 계열로만 열려 있다(2026-07-21 축소).

## 관련
- 실행기: [engine/core/tools.py](../../engine/core/tools.py) `RealToolExecutor`
- ✅ **Phase1 실검증 완료(2026-07-02)**: apply → `python -m engine.run_real` → destroy. 실 Bedrock Haiku가 `s3:GetBucketPolicy`·`s3:GetBucketPublicAccessBlock`을 **스스로 골라 호출**해 공개 버킷을 확인하고 CONFIRMED(100%) 판정 → 즉시 destroy(잔존 ~$0). 지금은 최소비용 회귀 픽스처로만 유지한다.
