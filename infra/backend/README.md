# infra/backend — 분석 백엔드 평면 (데이터 + 추론 + 조치)

> **원래 `infra/pipeline` + `infra/engine` 두 레이어였다가 2026-07-03에 하나로 합침.**
> 둘 다 shared만 참조하는 백엔드 Lambda 뭉치라, 레이어를 나눌 실익보다 단순함이 커서 병합.
> **코드 폴더(`pipeline/`·`engine/`·`attackpath/`)는 그대로** — 이건 '배포 껍데기'만 합친 것.

## 무엇을 배포하나 (한눈에)

```
[스캐너 findings]
   │  EventBridge (Security Hub Findings Imported)
   ▼
① ingest Lambda ──▶ SQS(+DLQ) ──▶ ② normalize Lambda ──▶ RDS(pgvector)     ← 데이터 평면
                                        │  PutEvents(cnapp.findings.batch.completed)
                                        ▼
                              ③ correlation Lambda(attackpath) ──▶ RDS       ← 추론 평면
                                        │  PutEvents(cnapp.attackpath.correlation.completed)
                                        ▼
                              ④ orchestrator Lambda ──▶ RDS(cases)
                                   (Triage→Hypothesis→Evidence[Bedrock tool-use]→Reasoning)

승인(approver) ──▶ console-backend ──StartExecution──▶ ⑤ remediation SFn         ← 조치(HITL)
                                                          └▶ remediation Lambda(격상 역할)
                                                                └▶ 불변 감사(S3 Object Lock)
```

## 리소스 목록 (배포되는 실체)

| 구역 | 리소스 | 설명 |
|---|---|---|
| **데이터 평면** | `aws_sqs_queue.ingest` (+ `ingest_dlq`) | ingest→normalize 버퍼 + DLQ(maxReceiveCount 5) |
| | `aws_lambda_function.ingest` | EventBridge/S3 이벤트 → 계약⑤ 봉투 → SQS |
| | `aws_lambda_function.normalize` | SQS 소비 → OCSF-lite 정규화 → RDS upsert → 배치완료 이벤트 발행 (VPC 배치) |
| | `aws_cloudwatch_event_rule.securityhub_imported` | Security Hub Findings Imported → ingest |
| **추론 평면** | `aws_lambda_function.correlation` | R1~R5 상관 → attack-path 그래프 upsert (VPC 배치) |
| | `aws_lambda_function.orchestrator` | Triage→Hypothesis→Evidence(Bedrock tool-use)→Reasoning → case upsert (VPC, Bedrock 정책) |
| | `aws_cloudwatch_event_rule.batch_completed` / `.correlation_completed` | 2-pass 트리거 체인 |
| **조치(HITL)** | `aws_sfn_state_machine.remediation` | 승인 후 조치 워크플로우(ValidateApproval→ApplyFix→RecordAudit) |
| | `aws_lambda_function.remediation` | 격상 역할 — S3 block·SG revoke·IAM diff (변경 API, 유일한 '쓰기' 경로) |
| | `aws_s3_bucket.audit` | 불변 감사 로그(Object Lock GOVERNANCE 1일·versioning·PAB·SSE) |
| **공통** | `aws_security_group.lambda` | 모든 VPC Lambda(normalize·correlation·orchestrator·remediation) 공용 egress SG |
| | IAM 역할 6종 | ingest·normalize·correlation·orchestrator·remediation·sfn (각 최소권한) |

## shared에서 읽는 것 (remote_state)
`vpc_id` · `private_subnet_ids` · `rds_endpoint` · `rds_secret_arn` · `evidence_readonly_policy_arn`(계약④ read-only allowlist) · `bedrock_invoke_policy_arn`.

## 이 레이어가 내보내는 것 (outputs)
- `remediation_state_machine_arn` → **infra/console**이 `-var`로 주입(approver 승인 시 StartExecution 대상)
- `audit_bucket` · `remediation_state_machine_arn` → **infra/monitoring**이 대시보드/알람에서 참조
- `ingest_queue_url`·`*_lambda_arn` 등 → 운영·디버깅용

## apply
```bash
cd infra/backend
terraform init
terraform plan -out=backend.tfplan   # 선행: infra/shared apply 완료(remote_state)
terraform apply backend.tfplan
```
- **선행:** `infra/shared`(VPC·RDS·evidence/bedrock 정책). 나머지 레이어(target·console)와는 **병렬 가능**(서로 참조 안 함).
- **후행 참조:** `infra/monitoring`은 이 레이어 apply 후에 plan 가능(remote_state).
- **RDS 스키마:** normalize/correlation/orchestrator는 findings·attack_paths·cases 테이블 필요 → shared apply 후 `psql -f infra/shared/db/schema.sql` 선적용([shared README](../shared/README.md)).

## Lambda 실코드 배포 (2026-07-03 스텁 스왑 완료)
모든 Lambda가 **실코드**를 배포한다. 빌드 = **`python infra/backend/build_lambdas.py`**(deploy.ps1이 backend apply/plan 전 자동 실행):
- `build/src-{pipeline,attackpath,engine}/` = 각 패키지 + `contracts/*.json`을 zip 루트에 나란히 배치 → 코드의 상대경로 해석(`normalizer._CATALOG_PATH` 등)이 무변경으로 동작.
- `build/layer/python/` = psycopg2-binary(manylinux2014_x86_64·cp312) → Lambda 레이어(RDS 접근 4함수 부착, ingest 제외).
- zip은 terraform `archive_file`이 생성(소스 해시 일관). `validate`는 archive를 평가 안 해 빌드 없이 통과, `plan/apply`는 빌드 디렉터리 필수.

| Lambda | handler | 레이어 | 비고 |
|---|---|---|---|
| ingest | `pipeline.ingest.handler.handler` | — | boto3만 (RDS 불요) |
| normalize | `pipeline.normalize.handler.handler` | psycopg2 | SQS→정규화→RDS upsert→batch.completed |
| correlation | `attackpath.correlation.handler.handler` | psycopg2 | R1~R5→attack_paths upsert→2-pass 발행 |
| orchestrator | `engine.handler.handler` | psycopg2 | `REAL_TOOLS=1`(기본) → 실 Bedrock tool-use |
| remediation | `engine.remediation.handler` | psycopg2 | 변경 API(dry-run/apply)+Object Lock 감사 |

로직 자체는 `run_e2e.py`·`run_real.py`로 로컬 검증됨(RDS/Bedrock 라이브 관통은 apply 세션). ⚠️ 실 RDS 테이블 필요 → shared apply 후 `psql -f infra/shared/db/schema.sql` 선적용.
