# infra/shared — 공유 기반 레이어 (Terraform)

> **레이어드 terraform의 0번 — 가장 먼저 apply.** 모든 상위 레이어(karpenter·target·backend·console·monitoring)가 이 출력을 참조한다(project-draft 4.6). 준형이 최초 apply.
>
> ✅ **현재 상태 = 라이브 검증 완료.** 아래 사전작업·`TODO` 마커는 전부 해소됐고, apply→검증→destroy 풀사이클을 여러 차례 실증했다(최근 2026-07-21 Bedrock IAM 축소 apply 포함). 비용 발생(EKS·RDS·NAT) — 데모 기간만 켜고 `destroy`.

## 무엇이 들어있나

> `.tf`는 3개로 단순화 — Terraform은 폴더 내 모든 `.tf`를 합쳐 읽으므로 리소스는 `main.tf` 한 파일에 **구역 주석**으로 묶고, 관례대로 `variables`·`outputs`만 분리.

| 파일 | 내용 |
|---|---|
| **`main.tf`** | 전체 리소스 — 구역: `[TF·BACKEND]`(버전·S3 백엔드 네이티브 락) · `[PROVIDER]` · `[VPC]`(2AZ, NAT GW 끔, Gateway Endpoint) · `[NAT]`(raw NAT Instance **t4g.micro** — t4g.nano는 이 계정 프리티어 제약으로 RunInstances 거부, 2026-07-03 실측) · `[EKS]`(spot t3.small·scale 0~2·IRSA) · `[ECR]`(4종, scan-on-push) · `[RDS]`(PG t3.micro+pgvector, Secrets Manager) · `[IAM-OIDC]`(GitHub OIDC, 키 없음 — ECR push 정책 + **`SecurityAudit`(AWS 관리형)·prowler 결과버킷 쓰기**[2026-07-07, `.github/workflows/prowler-scan.yml`용]) · `[IAM-ENGINE]`(Evidence read-only=계약④, Bedrock invoke) |
| `variables.tf` / `terraform.tfvars.example` | 입력 변수 + 예시 |
| `outputs.tf` | 하위 레이어가 참조할 출력(vpc·eks·ecr·rds·iam) |
| **`db/schema.sql`** | pgvector 데이터 스키마 DDL(계약①③⑦⑥ + console §5). RDS apply 후 **VPC 내부에서 1회 적용**(아래) — 실 데이터 평면(pipeline·engine·rag·console)의 테이블 전제 |

## DB 스키마 적용 (RDS apply 후)

RDS는 private subnet이라 로컬에서 직접 못 닿는다. **VPC 내부**(마이그레이션 Lambda / 배스천 / normalize·corpus 첫 실행)에서 멱등 SQL을 1회 적용:
```bash
# DSN은 Secrets Manager(rds_secret_arn) — VPC 내부 셸에서
psql "$PG_DSN" -f db/schema.sql   # CREATE EXTENSION vector + 7개 테이블(IF NOT EXISTS — findings·attack_paths·cases·finding_explanations·remediation_requests·rag_chunks·login_events)
```

## apply 전 사전작업 (필수)

1. **state 버킷 부트스트랩** — manual-infra.md 2번. S3 버킷 1개(버저닝·SSE·public 차단). 만든 뒤:
   - `main.tf` `[TF·BACKEND]` 구역의 `bucket` 값 교체, 또는 `terraform init -backend-config="bucket=..."`.
2. ✅ **Bedrock 모델 액세스** — 완료. '모델 액세스' 페이지는 폐지(retired)됐고 서버리스 모델은 첫 호출 시 자동 활성, Anthropic만 최초 1회 use-case 제출이 필요했다(manual-infra §4). 사용 모델은 Titan Embed v2 + Claude Haiku 4.5(**global inference profile**).
   - ✅ **모델 ARN 좁히기도 완료(2026-07-21)** — `bedrock_invoke` 정책이 `"*"` → 실사용 계열로 축소. ⚠️ **global inference profile은 여러 리전으로 라우팅하므로 파운데이션 모델 ARN에 리전 와일드카드가 필수**다(리전을 고정하면 라우팅된 호출이 AccessDenied). 실호출로 검증함.
3. ✅ **TODO 마커** — 전부 해소. `cluster_admin_principal_arns`(jh_lee·jw_kim), `github_repo` 확정. `nat_ami_owner`(`568608671756`)는 fck-nat 공식 문서와 대조 검증 완료(2026-07-21).
   - ⚠️ 남은 의도적 트레이드오프: **RDS SG를 소스 SG로 못 좁힘** — RDS SG는 이 레이어 소유인데 접속 주체 Lambda SG는 `infra/backend`가 만들어 **레이어 순환**이다. backend에서 규칙을 주입하면 풀리지만 apply 순서 중 DB 연결이 끊긴다. 완화: private subnet 전용 + Secrets Manager + `sslmode=require`.
4. ✅ **fck-nat 모듈 변수 검증** — 완료(라이브 apply로 실증).

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

- NAT Instance(t4g.micro) ~$3/월 · RDS t3.micro free tier(이후 ~$13/월) · EKS 컨트롤플레인 $0.10/h · spot 노드.
- 비데모: EKS 노드 scale-to-0, RDS Stop(+EventBridge 재-Stop — `main.tf` `[RDS]` 구역 TODO), 완전 비사용 시 `destroy`.
- Budgets $50/$100 알림 유지(manual-infra).

## 다음 레이어

이 출력을 `terraform_remote_state`로 읽어 `infra/karpenter`·`infra/target`·`infra/backend`·`infra/console`(준형) + `infra/monitoring`(**진우**)이 위에 쌓는다 — 전부 라이브 apply 검증 완료. `infra/slice`는 레이어가 아닌 저비용 검증 픽스처(독립).
