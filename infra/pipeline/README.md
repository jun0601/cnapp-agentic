# infra/pipeline — 수집·정규화 데이터 평면

> project-draft §4.6 · console-app-design §9. **shared 다음** 레이어.
> 스캐너 findings를 받아 OCSF-lite로 정규화해 pgvector에 적재하는 **이벤트 배관**.

## 흐름
```
[스캐너 findings] → EventBridge(기본 버스, Security Hub Findings Imported)
     → ingest Lambda → SQS(cnapp-ingest, +DLQ)
     → normalize Lambda(SQS 소비) → OCSF-lite 정규화 → RDS(pgvector)
     → PutEvents(source=cnapp.findings / detail-type=cnapp.findings.batch.completed)
          → infra/engine 상관 Lambda가 구독(2-pass 트리거)
```

## 무엇을 만드나
- **SQS** `cnapp-ingest` + DLQ (재시도·백프레셔)
- **ingest Lambda** — EventBridge/S3 이벤트 → 계약⑤ 봉투 → SQS (`pipeline/ingest`)
- **normalize Lambda** — SQS 소비 → `Normalizer`로 OCSF-lite 변환 → RDS (`pipeline/normalize`), VPC 배치(RDS 접근)
- **EventBridge 규칙** — `aws.securityhub` "Findings - Imported" → ingest

## ⚠️ Lambda 패키지 (실 apply/CI 전 확인)
지금 Lambda는 **배포 가능한 스텁**(`index.handler`, 이벤트 로깅 후 200). 비즈니스 로직은
`run_e2e.py`로 로컬 검증됨 — 이 레이어는 **프로덕션 배관 모양**을 정의한다.
실 전환 = `data.archive_file`의 `source`를 `pipeline/ingest`·`pipeline/normalize` 빌드
산출물(코드 + deps + `contracts/*.json` 번들)로 교체(CI 빌드 스텝).

## apply (레이어드 · 테스트 후 destroy)
```bash
cd infra/pipeline
terraform init      # --backend-config 없이(백엔드 하드코딩) · profile은 AWS_PROFILE
terraform validate
terraform apply     # shared apply 선행 필수(remote_state 참조)
# ... 테스트 ...
terraform destroy
```

## 의존
- **선행:** `infra/shared`(VPC·private subnet·RDS·Secrets) — remote_state로 참조.
- **후행:** `infra/engine`(상관·오케스트레이터 Lambda가 `cnapp.findings.batch.completed` 구독).
