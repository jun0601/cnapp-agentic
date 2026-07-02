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
#   (엔진 쪽 실 LLM 플래너는 준형과 함께 붙일 부분)

terraform destroy -var 'profile=cnapp'         # ★ 테스트 끝나면 즉시
```

## ⚠️ apply 시 확인 (준형과)
- **계정 레벨 S3 Block Public Access**가 켜져 있으면 공개 정책 apply가 거부될 수 있음
  → `-var 'enable_public_policy=false'`로 두면 PAB-off 신호만으로도 tool-use 데모 가능
  (RealToolExecutor는 `GetPublicAccessBlock`에서 '차단 없음'을 관측).
- **RealToolExecutor의 신원**(로컬 `cnapp` 프로파일 또는 전용 역할)이 `s3:GetBucketPolicy`·
  `s3:GetPublicAccessBlock` 권한을 가져야 함(계약④ evidence-allowlist 범위).
- **Bedrock 모델 액세스**(Claude Haiku)는 별도 콘솔 승인 필요 — 실 model ID/리전 확정은 apply 때.

## 관련
- 실행기: [engine/core/tools.py](../../engine/core/tools.py) `RealToolExecutor`
- 상세 실행 플랜은 클로드 메모리(vertical-slice-plan)에 체크리스트로 보관.
