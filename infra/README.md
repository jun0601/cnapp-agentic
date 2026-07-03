# infra/ — Terraform 레이어드 인프라 (전체 개요)

> **레이어별 상세는 각 하위 README** — 이 문서는 "전체가 어떻게 조립되나 + apply를 어떤 순서·규율로 하나"의 단일 개요다. 설계 근거 = [project-draft §4.6](../docs/project-draft.md).

---

## 🧱 1. 레이어링 개념 (왜 폴더를 나눴나)

**한 덩어리 terraform이 아니라 레이어별 독립 state**로 나눈다:

```
                    ┌─ infra/karpenter (동적 노드 오토스케일러 — 클러스터 런타임: helm·CRD)
                    ├─ infra/target    (취약 워크로드 결함 IaC — 휘발성·격리)
infra/shared ───────┤
(VPC·EKS·RDS·       ├─ infra/backend   (분석 백엔드: 수집·정규화 + 상관·오케스트레이터 + 조치 SFn·감사) ─┐
 NAT·ECR·OIDC·IAM)  └─ infra/console   (관제 앱: ALB·Cognito SSO·CloudFront·Lambda) ─────────────────────┴─→ infra/monitoring
                       ※ monitoring = shared + backend·console 출력 참조 → 이 셋 다음 '마지막' apply       (관측: 대시보드·CloudTrail·Teams)

# infra/backend = 구 infra/pipeline + infra/engine 병합(2026-07-03) — 둘 다 백엔드 Lambda 뭉치라 단순화. 코드 폴더(pipeline/·engine/)는 그대로.
# infra/karpenter = 구 infra/shared/karpenter.tf 분리(2026-07-03) — shared를 '순수 AWS 폴대'로 유지하려 클러스터 런타임(helm/kubectl provider)을 별 레이어로 격리. shared엔 discovery 태그만 남김.
(별도) infra/slice — ★레이어 아님. 엔진 실 tool-use 최소비용(<$1) 검증용 일회용 픽스처(독립 스택)
```

- **참조 방향:** 상위 레이어가 `terraform_remote_state`로 하위 레이어의 **출력(outputs)만 읽는다**(수정 불가) — `karpenter`·`target`·`backend`·`console`은 shared만, `monitoring`만 shared + backend·console도 참조. → shared가 반드시 **먼저**, monitoring이 **마지막** apply.
- **⚠️ 순서는 `infra/deploy.ps1`이 강제한다**(2026-07-03 신설) — apply는 정방향, destroy는 역방향으로 자동 순회. 순서를 손으로 어겨 사고 난 전례(destroy 때 shared를 target보다 먼저 지워 remote_state 깨짐)를 코드로 차단. 사용법 = 아래 §3.5.
- **왜 나눴나:** ① state 격리 = **blast-radius 축소**(한 레이어 실수가 남을 안 부숨) ② destroy도 레이어 단위(휘발성 target만 자주 부수기) ③ 두 사람이 서로 다른 레이어를 동시에 만져도 락 충돌 없음.
- **state 백엔드:** S3 버킷 1개(`cnapp-agentic-tfstate`) + 레이어별 key(`infra/<레이어>/terraform.tfstate`) + `use_lockfile`(S3 네이티브 락 — DynamoDB 불필요, TF ≥1.10). slice만 로컬 state(일회용).

## 📋 2. 레이어 표

> **전 6레이어 라이브 풀사이클 실검증 완료(2026-07-03):** `deploy.ps1 -Action apply` 원샷 207개 생성 → Karpenter 노드 프로비저닝·consolidation 실증 → 역순 destroy 208개·잔존 $0.

| 레이어 | 내용 | 주요 과금 | 코드 상태 |
|---|---|---|---|
| `shared/` | VPC·NAT Instance·EKS·ECR·RDS pgvector·GitHub OIDC·엔진 IAM 2종 + **`db/schema.sql`**(pgvector 6테이블). **discovery 태그만 부착**(Karpenter 실체는 별 레이어) | **EKS $0.10/h**·NAT ~$3/월(t4g.micro=프리티어)·RDS(프리티어) | ✅ 라이브 apply→destroy 실검증 |
| `karpenter/` | Karpenter 서브모듈(컨트롤러 IRSA·노드 IAM·spot 중단 SQS) + helm_release(**1.13.0**, replicas 1) + EC2NodeClass·NodePool(t3.small/micro spot) | Karpenter가 띄운 노드 실비(스팟, 데모선 미미) | ✅ **전체 수명주기 실증**(프로비저닝 ~30초·consolidation 회수, [README §4](karpenter/README.md)) |
| `target/` | 의도적 결함 토글(f3 open SG·f4 과도 IRSA·f6 공개 S3) — `enable_*` var | S3 몇 센트 | ✅ 라이브 실검증 |
| `backend/` | **수집·정규화**(SQS·ingest/normalize Lambda) + **상관·오케스트레이터** Lambda(2-pass) + **조치** remediation SFn·감사 Object Lock 버킷 — *구 pipeline+engine 병합* | 무료급 + Bedrock 호출당 | ✅ 라이브 실검증(ENI 함정 하드닝 반영) |
| `console/` | S3+CloudFront(OAC)·Cognito(Entra SAML)·ALB(authenticate-cognito)→Lambda | ALB ~$0.03/h·CF/Lambda 무료급 | ✅ 라이브 실검증(CloudFront 200) |
| `monitoring/` | Grafana IRSA·CloudWatch 대시보드 24위젯·CloudTrail→Logs 배관·Teams 알림(SNS·Lambda·알람7) | 무료급(대시보드·로그량) | ✅ 라이브 실검증 (**shared+backend+console 후**) |
| `slice/` | 공개 S3 1개+가짜 PII 1개(엔진 실 tool-use 표적) | 몇 센트 | ✅ Phase1 실검증 완료 |

## 🔁 3. apply 규율 (비용 = 켜둔 시간)

```
preflight(무과금) → plan(무과금 미리보기) → 리뷰 → apply(과금 시작) → 검증 → destroy(과금 끝)
```

1. **plan 없이 apply 금지.** plan이 provider 검증(예: SG description charset)을 apply 전에 잡는다 — 돈 쓰기 전에 걸러짐.
2. **apply 순서 = ① shared → ② karpenter(클러스터가 있어야 함) → ③ (target | backend | console — shared만 참조라 병렬 가능) → ④ monitoring(마지막) → 검증 → 역순 destroy(monitoring → target·backend·console → karpenter → shared).** ← **이 순서를 `infra/deploy.ps1`이 강제**(§3.5).
   ⚠️ **의존 레이어의 plan은 그 하위 레이어 apply 후에만 가능** — `terraform_remote_state`가 실제 S3 state를 읽기 때문(하위 state 없으면 outputs가 비어 참조 에러 = 코드 버그 아님·구조적 제약). 특히 monitoring plan은 backend·console state가, karpenter plan은 shared state(+라이브 EKS 클러스터)가 있어야 함.
3. **검증 끝나면 즉시 destroy.** 실질 과금은 거의 EKS 컨트롤플레인($0.10/h) — 1~2시간 세션이면 총 몇 센트~$0.3.
4. **EKS 첫 apply 직전 1회 확인**(팀 규율) — 과금 시작점.
5. **destroy 순서·함정 (리뷰 2026-07-02·07-03 반영):**
   - **karpenter는 shared '직전'에 destroy**(deploy.ps1 역순이 자동 처리) — NodePool을 지우면 Karpenter가 자기 노드를 드레인한 뒤 helm이 제거된다. shared(=EKS)를 먼저 지우면 karpenter destroy가 라이브 클러스터·remote_state를 못 읽어 실패하고, Karpenter가 띄운 노드가 고아로 남아 VPC/EKS destroy를 막는다.
   - **EKS를 apply해 ArgoCD가 `Service type=LoadBalancer`로 배포했다면**, `terraform destroy` 전에 **k8s LB 서비스부터 삭제(또는 ArgoCD 앱 prune)** — 안 그러면 terraform 밖에서 생긴 ELB/ENI가 서브넷을 잡아 shared destroy가 `DependencyViolation`으로 실패(고전적 EKS destroy 함정).
   - **Lambda VPC ENI 지연**: backend/console의 VPC Lambda는 destroy 시 Hyperplane ENI가 함수 삭제 후에도 SG를 붙잡는다(AWS 플랫폼 동작 — 2026-07-03 라이브 실측: `in-use`→`available` 전환까지 **~25분**). Lambda SG에 `timeouts { delete = "40m" }`를 넣어 **원샷 destroy 되도록 하드닝됨**(기본 15분이면 실패 후 재실행 필요했음). **가속 절차(실측 검증)**: `aws ec2 describe-network-interfaces --filters "Name=group-id,Values=<SG_ID>"`로 상태 확인 → `available`이면(detach 완료) `aws ec2 delete-network-interface`로 수동 삭제 → terraform의 SG 재시도가 수십 초 내 통과. (`in-use`인 동안엔 Lambda 서비스 소유라 강제 삭제 불가 — 대기가 유일한 경로.)
   - **감사 버킷(backend)** — 실 remediation을 돌려 감사 객체가 쓰였으면 Object Lock(GOVERNANCE 1일) 보존 내라 destroy 실패 → `aws s3api delete-object ... --bypass-governance-retention`로 먼저 비우기(핵심 데모는 감사 객체 안 씀 → 대개 무해).
   - RDS 마스터 시크릿은 `recovery_window_in_days=0`으로 즉시 삭제(재-apply 이름 충돌 방지, 코드 반영됨).

### 3.5 순서 강제 실행기 `infra/deploy.ps1` (2026-07-03 신설·같은 날 라이브 실검증)

레이어 순서를 손으로 어겨 사고 난 전례(destroy 때 shared를 target보다 먼저 지워 `remote_state.shared` 붕괴)를 **코드로 차단**. apply는 정방향, destroy는 역방향으로 자동 순회하고, **중간 레이어가 실패하면 즉시 멈춘다**(그다음 레이어를 건드려 상태를 더 망가뜨리지 않음). **라이브 실검증(2026-07-03): apply 원샷 6레이어 207개(exit 0) · destroy 역순 208개 — 실패-중단(shared IGW 레이스 1회)→해당 레이어만 재실행 흐름까지 설계대로 동작 확인.**

```powershell
./infra/deploy.ps1 -Action validate                 # 전 레이어 문법검사(무과금·클라우드 접근 없음)
./infra/deploy.ps1 -Action apply                     # shared→karpenter→target→backend→console→monitoring (각 수동 승인)
./infra/deploy.ps1 -Action apply   -AutoApprove      # 승인 생략
./infra/deploy.ps1 -Action destroy -AutoApprove      # 역순: monitoring→...→karpenter→shared
./infra/deploy.ps1 -Action apply   -Layer shared     # 단일 레이어만
./infra/deploy.ps1 -Action apply   -Layer console -ExtraArgs '-var','enable_custom_domain=true'  # SSO 커스텀도메인
```

- **동작:** 각 레이어 폴더로 `Push-Location` 후 `terraform init`(+validate/plan/apply/destroy). `-chdir=<한글 절대경로>`를 인자로 넘기지 않는다 — PowerShell→exe 인자 인코딩에서 한글 경로가 깨지기 때문.
- **⚠️ 이 스크립트는 의도적으로 ASCII 전용**이다. Windows PowerShell 5.1은 BOM 없는 UTF-8 `.ps1`을 시스템 코드페이지(한글=cp949)로 읽어, 한글 주석의 멀티바이트가 **바로 다음 코드 라인을 삼켜** 명령이 실행 안 되는 함정이 있다(2026-07-03 확인·수정). 그래서 스크립트 본문은 영어 주석, 상세 한글 설명은 이 README에 둔다. **재편집 시에도 ASCII 유지**(비-ASCII 넣으면 다시 깨짐).
- **AWS 프로파일:** `-AwsProfile cnapp`처럼 지정(미지정 시 환경 자격증명). `PS7(pwsh)`에서 돌리면 인코딩 함정 자체가 없다(참고).

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
