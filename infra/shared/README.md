# infra/shared — 공유 기반 레이어 (Terraform)

> **레이어드 terraform의 0번 — 가장 먼저 apply.** 모든 영역(target·console·scanners·pipeline·engine)이 이 출력을 참조한다(project-draft 4.6). 준형이 최초 apply.
>
> ⚠️ **현재 상태 = 스캐폴드.** apply 전 아래 사전작업 + `TODO` 마커를 채우고 리뷰해야 한다. 비용 발생(EKS·RDS·NAT) — 데모 기간만 켜고 `destroy`.

## 무엇이 들어있나

> `.tf`는 3개로 단순화 — Terraform은 폴더 내 모든 `.tf`를 합쳐 읽으므로 리소스는 `main.tf` 한 파일에 **구역 주석**으로 묶고, 관례대로 `variables`·`outputs`만 분리.

| 파일 | 내용 |
|---|---|
| **`main.tf`** | 전체 리소스 — 구역: `[TF·BACKEND]`(버전·S3 백엔드 네이티브 락) · `[PROVIDER]` · `[VPC]`(2AZ, NAT GW 끔, Gateway Endpoint) · `[NAT]`(raw NAT Instance t4g.nano) · `[EKS]`(spot t3.small·scale 0~2·IRSA) · `[ECR]`(4종, scan-on-push) · `[RDS]`(PG t3.micro+pgvector, Secrets Manager) · `[IAM-OIDC]`(GitHub OIDC, 키 없음) · `[IAM-ENGINE]`(Evidence read-only=계약④, Bedrock invoke) |
| `variables.tf` / `terraform.tfvars.example` | 입력 변수 + 예시 |
| `outputs.tf` | 하위 레이어가 참조할 출력(vpc·eks·ecr·rds·iam) |
| **`db/schema.sql`** | pgvector 데이터 스키마 DDL(계약①③⑦⑥ + console §5). RDS apply 후 **VPC 내부에서 1회 적용**(아래) — 실 데이터 평면(pipeline·engine·rag·console)의 테이블 전제 |

## DB 스키마 적용 (RDS apply 후)

RDS는 private subnet이라 로컬에서 직접 못 닿는다. **VPC 내부**(마이그레이션 Lambda / 배스천 / normalize·corpus 첫 실행)에서 멱등 SQL을 1회 적용:
```bash
# DSN은 Secrets Manager(rds_secret_arn) — VPC 내부 셸에서
psql "$PG_DSN" -f db/schema.sql   # CREATE EXTENSION vector + 6개 테이블(IF NOT EXISTS)
```

## apply 전 사전작업 (필수)

1. **state 버킷 부트스트랩** — manual-infra.md 2번. S3 버킷 1개(버저닝·SSE·public 차단). 만든 뒤:
   - `backend.tf`의 `bucket` 값 교체, 또는 `terraform init -backend-config="bucket=..."`.
2. **Bedrock 모델 액세스** — 콘솔에서 서울(ap-northeast-2) 리전에 Claude Haiku/Sonnet·Titan Embed v2 **모델 액세스 요청**(승인까지 시간 소요 가능). 가용성 실측 후 `iam-engine.tf`·`variables.tf`의 모델 ARN 좁히기.
3. **TODO 마커 채우기** — `cluster_admin_principal_arns`(jh_lee·jw_kim ARN), `github_repo`, NAT/모델 ARN 등.
4. **fck-nat 모듈 변수 검증** — 고정 버전(`~> 1.3`) 문서로 변수명 확인.

## apply 순서

```bash
cd infra/shared
cp terraform.tfvars.example terraform.tfvars   # 값 채우기
terraform init -backend-config="bucket=<state-bucket>"
terraform plan      # 반드시 리뷰
terraform apply     # 비용 발생 시작
# ...데모 종료 후...
terraform destroy   # 비용 0
```

## 비용 메모 (project-draft 22번)

- NAT Instance(t4g.nano) ~$3/월 · RDS t3.micro free tier(이후 ~$13/월) · EKS 컨트롤플레인 $0.10/h · spot 노드.
- 비데모: EKS 노드 scale-to-0, RDS Stop(+EventBridge 재-Stop, rds.tf TODO), 완전 비사용 시 `destroy`.
- Budgets $50/$100 알림 유지(manual-infra).

## 다음 레이어

이 출력을 `terraform_remote_state`로 읽어 `infra/target`·`infra/console`·`infra/pipeline`·`infra/engine`(전부 준형/영역 주인, **코드 완성·validate 통과**)이 위에 쌓는다. `infra/slice`는 레이어가 아닌 저비용 검증 픽스처(독립).
