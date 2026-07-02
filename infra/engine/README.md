# infra/engine — 에이전틱 분석 평면 + 조치(HITL)

> project-draft §4.6 · §17(HITL) · console-app-design §6·§14. **shared·pipeline 다음** 레이어.
> 프로젝트 심장(능동조사) + 크로스클라우드 상관 + 승인형 조치의 **서버리스 배관**.

## 흐름 (2-pass, console-app-design §14)
```
정규화 배치 완료  cnapp.findings.batch.completed(EventBridge)
   → 상관 Lambda(attackpath): R1~R5 → attack-path 그래프 upsert(RDS)
   → PutEvents cnapp.attackpath.correlation.completed
   → 오케스트레이터 Lambda(engine): Triage→Hypothesis→Evidence(tool-use)→Reasoning
        → case(계약⑦) upsert(RDS)
```
- **Evidence(오케스트레이터)** = 실 tool-use. shared의 **evidence read-only allowlist(계약④)** + **Bedrock invoke** 정책을 role에 attach. model ID = `global.anthropic.claude-haiku-4-5-...`(manual-infra §4). Phase1에서 `run_real`로 **실검증 완료**.

## 조치(HITL, §17)
```
콘솔 approver 승인 → console-backend가 이 Step Functions StartExecution
   → ValidateApproval → ApplyFix(remediation Lambda, 격상 역할) → RecordAudit
```
- MVP 카탈로그 3종(§24): **S3 public block · open SG(0.0.0.0) 제거 · IAM diff**.
- **격상 권한(변경 API)은 remediation Lambda 역할에만** — 콘솔/분석 역할은 read-only(§17 최소권한 분리).

## ⚠️ Lambda 패키지 (실 apply/CI 전)
Lambda 3종(correlation·orchestrator·remediation) = **배포 가능한 스텁**. 로직은 `run_e2e`·`run_real`로
로컬 검증됨. 실 전환 = `data.archive_file`의 `source`를 실코드 빌드 산출물로 교체(CI).

## apply
```bash
cd infra/engine
terraform init && terraform validate
terraform apply    # shared 선행 필수(evidence·bedrock 정책·RDS remote_state)
# console에 넘길 값:
terraform output remediation_state_machine_arn
terraform destroy
```

## 의존
- **선행:** `infra/shared`(RDS·evidence/bedrock 정책), `infra/pipeline`(배치 완료 이벤트 발행처 — 이벤트는 기본 버스라 순서 강제는 아님).
- **후행:** `infra/console`(remediation SM ARN 참조 — output → -var 주입).
