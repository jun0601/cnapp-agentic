# infra/ — Terraform 레이어드 인프라 (전체 개요)

> **레이어별 상세는 각 하위 README** — 이 문서는 "전체가 어떻게 조립되나 + apply를 어떤 순서·규율로 하나"의 단일 개요다. 설계 근거 = [project-draft §4.6](../docs/project-draft.md).

---

## 🧱 1. 레이어링 개념 (왜 폴더를 나눴나)

**한 덩어리 terraform이 아니라 레이어별 독립 state**로 나눈다:

```
                    ┌─ infra/target    (취약 워크로드 결함 IaC — 휘발성·격리)
infra/shared ───────┼─ infra/console   (관제 앱: ALB·Cognito SSO·CloudFront·Lambda)
(VPC·EKS·RDS·       ├─ infra/pipeline  (수집·정규화: EventBridge→SQS→Lambda)
 NAT·ECR·OIDC·IAM)  └─ infra/engine    (상관·오케스트레이터·조치 SFn·감사 Object Lock)

(별도) infra/slice — ★레이어 아님. 엔진 실 tool-use 최소비용(<$1) 검증용 일회용 픽스처(독립 스택)
```

- **참조 방향:** 상위 레이어가 `terraform_remote_state`로 shared의 **출력(outputs)만 읽는다**(수정 불가). → shared가 반드시 **먼저 apply**.
- **왜 나눴나:** ① state 격리 = **blast-radius 축소**(한 레이어 실수가 남을 안 부숨) ② destroy도 레이어 단위(휘발성 target만 자주 부수기) ③ 두 사람이 서로 다른 레이어를 동시에 만져도 락 충돌 없음.
- **state 백엔드:** S3 버킷 1개(`cnapp-agentic-tfstate`) + 레이어별 key(`infra/<레이어>/terraform.tfstate`) + `use_lockfile`(S3 네이티브 락 — DynamoDB 불필요, TF ≥1.10). slice만 로컬 state(일회용).

## 📋 2. 레이어 표

| 레이어 | 내용 | 주요 과금 | 코드 상태 |
|---|---|---|---|
| `shared/` | VPC·NAT Instance·EKS·ECR·RDS pgvector·GitHub OIDC·엔진 IAM 2종 + **`db/schema.sql`**(pgvector 6테이블) | **EKS $0.10/h**·NAT ~$3/월·RDS(프리티어) | ✅ plan 클린(74 add) |
| `target/` | 의도적 결함 토글(f3 open SG·f4 과도 IRSA·f6 공개 S3) — `enable_*` var | S3 몇 센트 | ✅ validate (plan은 shared 후) |
| `console/` | S3+CloudFront(OAC)·Cognito(Entra SAML)·ALB(authenticate-cognito)→Lambda | ALB ~$0.03/h·CF/Lambda 무료급 | ✅ validate (〃) |
| `pipeline/` | EventBridge→SQS+DLQ→ingest/normalize Lambda(VPC) | 무료급(호출량) | ✅ validate (〃) |
| `engine/` | 상관·오케스트레이터 Lambda·remediation SFn·감사 Object Lock 버킷 | 무료급 + Bedrock 호출당 | ✅ validate (〃) |
| `slice/` | 공개 S3 1개+가짜 PII 1개(엔진 실 tool-use 표적) | 몇 센트 | ✅ Phase1 실검증 완료 |

## 🔁 3. apply 규율 (비용 = 켜둔 시간)

```
preflight(무과금) → plan(무과금 미리보기) → 리뷰 → apply(과금 시작) → 검증 → destroy(과금 끝)
```

1. **plan 없이 apply 금지.** plan이 provider 검증(예: SG description charset)을 apply 전에 잡는다 — 돈 쓰기 전에 걸러짐.
2. **apply 순서 = shared → (target | console | pipeline | engine 병렬 가능) → 검증 → 역순 destroy.**
   ⚠️ **의존 레이어의 plan은 shared apply 후에만 가능** — `terraform_remote_state`가 실제 S3 state를 읽기 때문(shared state 없으면 outputs가 비어 참조 에러 = 코드 버그 아님·구조적 제약).
3. **검증 끝나면 즉시 destroy.** 실질 과금은 거의 EKS 컨트롤플레인($0.10/h) — 1~2시간 세션이면 총 몇 센트~$0.3.
4. **EKS 첫 apply 직전 1회 확인**(팀 규율) — 과금 시작점.
5. **destroy 순서·함정 (리뷰 2026-07-02 반영):**
   - **EKS를 apply해 ArgoCD가 `Service type=LoadBalancer`로 배포했다면**, `terraform destroy` 전에 **k8s LB 서비스부터 삭제(또는 ArgoCD 앱 prune)** — 안 그러면 terraform 밖에서 생긴 ELB/ENI가 서브넷을 잡아 shared destroy가 `DependencyViolation`으로 실패(고전적 EKS destroy 함정).
   - **감사 버킷(engine)** — 실 remediation을 돌려 감사 객체가 쓰였으면 Object Lock(GOVERNANCE 1일) 보존 내라 destroy 실패 → `aws s3api delete-object ... --bypass-governance-retention`로 먼저 비우기(핵심 데모는 감사 객체 안 씀 → 대개 무해).
   - RDS 마스터 시크릿은 `recovery_window_in_days=0`으로 즉시 삭제(재-apply 이름 충돌 방지, 코드 반영됨).

## ✅ 4. preflight 체크리스트 (apply 세션 시작 시)

```bash
aws sts get-caller-identity            # 계정 066107819776 / jh_lee 확인
aws configure get region               # ap-northeast-2(서울)
aws s3 ls s3://cnapp-agentic-tfstate   # state 버킷 존재
# ⚠️ 버전 시한폭탄 재확인(리전·시점 의존 — apply-time 실패):
aws eks describe-cluster-versions --region ap-northeast-2 --query "clusterVersions[?status=='STANDARD_SUPPORT'].clusterVersion"  # eks_version이 STANDARD인지(EXTENDED=6배 과금)
aws rds describe-db-engine-versions --engine postgres --region ap-northeast-2 --query "DBEngineVersions[?starts_with(EngineVersion,'16.')].EngineVersion"  # db_engine_version 가용 확인
cd apps/console-backend && npm ci && npm run build   # ⚠️ console archive_file은 dist/ 필요 — 없으면 console plan부터 실패
# shared: terraform init -reconfigure → plan → 리뷰 → apply
```
- Bedrock 모델 액세스 ✅(manual-infra §4) · fck-nat AMI owner `568608671756` 검증 ✅(2026-07-02) · EKS 1.34·RDS 16.9 = 표준지원/가용(2026-07-02 확인, apply 지연 시 재확인).
- **Lambda 실코드 스왑**: 현재 Lambda들은 배포 가능한 스텁 — 실코드(각 `handler.py`·`engine/remediation.py`)+psycopg2 레이어로 교체는 CI 빌드 스텝(각 레이어 README).
- **RDS 스키마**: shared apply 후 VPC 내부에서 `psql -f shared/db/schema.sql` 1회(멱등) — [shared README](shared/README.md).
- **console SSO(apply 후 2건)**: ① Entra 앱 식별자를 `urn:amazon:cognito:sp:<user_pool_id>`로 갱신(placeholder면 로그인 실패, manual-infra §3.6.5) ② ACM 인증서 없으면 HTTP로 apply(count 가드) — **cert 없는 HTTP 모드는 무인증 노출**이라 ALB SG를 운영자 IP로 좁히기.

## 💰 5. 비용 근거

상세 결정 원장 = [docs/cost-strategy.md](../docs/cost-strategy.md). 요지: **진짜 절감 = destroy 규율 + spot**. NAT Gateway($32/월) 대신 NAT Instance(~$3/월), Aurora 대신 RDS t3.micro, 오토스케일은 Karpenter(포폴·모던 아키텍처 이유 — 데모 규모선 실비 영향 적음, §2.7에 정직하게 명시).
