# 수동 관리 리소스 현황 (Manual Infrastructure Log)

> **이 문서의 범위:** AWS 콘솔·Azure 포털·CLI로 **직접 생성·설정한 리소스만** 기록한다 — Terraform이 관리하는 리소스(VPC·EKS·Lambda·RDS·ALB 등)는 여기 쓰지 않는다.
>
> **수동 관리 대상 유형:**
> 1. **계정·테넌트 초기 설정** — Terraform 실행 전 사람이 먼저 해야 하는 것 (MFA, 루트 잠금, IAM 사용자 등)
> 2. **Terraform 부트스트랩 리소스** — Terraform 자체가 state를 저장하는 곳 (S3 state 버킷·DynamoDB 락), chicken-and-egg라 Terraform 밖에서 만들어야 함
> 3. **Terraform 외부 관리 항목** — 설계상 Terraform으로 관리하지 않는 것 (Azure SSO·Entra 앱 등록 등)
>
> 실제로 생성·완료한 뒤에만 갱신. "설계가 아닌 현황" 기록이므로 설계 문서([project-draft.md](project-draft.md))와 별개로 관리.

> **담당 (누가 하나) — 요약:**
> | 영역 | 담당 | 상태 |
> |---|---|---|
> | §1 AWS 계정 초기 설정 | **준형**(공유 인프라 주도) | ✅ 완료 |
> | §2 Terraform 부트스트랩(state 버킷) | **진우** | ✅ 완료 |
> | §3 Azure / Entra ID 초기 설정 | **진우**(신원 영역 주인) | 🔄 **진행 중**(M365/Entra 데모 테넌트 생성) |
> | §4 AWS Bedrock 모델 액세스 | **준형**(AWS·엔진 Evidence) | ✅ 완료 |
>
> *원칙: AWS 워크로드·부트스트랩은 준형 주도, Azure(신원=Entra)는 진우가 전담. 상세는 아래 각 절.*

---

## 1. AWS 계정 초기 설정 — ✅ 완료 (담당: 진우)

> project-draft.md D1~D3(11번) 가드레일 그대로 반영. 협업자도 이 상태를 전제로 작업 시작.

| 영역 | 설정 내용 | 담당 | 상태 |
|---|---|---|---|
| **계정 기본** | 단일 계정, 콘솔 기본 리전 **서울(ap-northeast-2)**. 계정 별칭 설정 완료. Organizations/Identity Center/Control Tower **미활성 확인됨**. | 준형 | ✅ |
| **루트 계정** | MFA(가상 MFA 앱) 활성화. 액세스 키 없음(보유 시 즉시 삭제). 이후 비상용(결제 변경 등)으로만 사용. | 준형 | ✅ |
| **결제 가드레일** | IAM 사용자/역할의 결제 정보 액세스 활성화. Free Tier 알림 ON. AWS Budgets **$50/$100** 2단계 알림(임계 80%/100%, 본인+협업자 이메일). | 준형 | ✅ |
| **IAM 사용자** | `Admins` 그룹(`AdministratorAccess`) 생성. 사용자: **`jw_kim`(진우)·`jh_lee`(준형)** — 모두 그룹 소속. **각자 MFA 필수.** 장기 Access Key 미발급 원칙(CLI는 임시 자격증명만). | 준형(생성)·각자(MFA) | ✅ |
| **CloudTrail** | 멀티 리전 트레일 생성(D2 전 리전 수집). 관리 이벤트 읽기/쓰기 활성화. 암호화 SSE-S3(기본). 로그 파일 검증 ON. SNS·CloudWatch Logs 연동 OFF. | 준형 | ✅ |

---

## 2. Terraform 부트스트랩 리소스 — ✅ state 버킷 완료 (담당: 진우)

> Terraform이 state를 저장하기 위해 **Terraform 실행 전** 콘솔/CLI로 먼저 만들어야 하는 리소스. 이후 Terraform이 직접 관리하지 않는다.
> `infra/` 폴더별 state 파일을 분리하기 위해 버킷 1개 + prefix 방식 사용.

| 리소스 | 내용 | 담당 | 상태 |
|---|---|---|---|
| **S3 state 버킷** | 이름 = **`cnapp-agentic-tfstate`** (서울, ap-northeast-2). Terraform state + 네이티브 락. 버저닝 ON·SSE-S3(AES256)·public access 4종 차단 **검증 완료(2026-07-01)**. `infra/{shared,target,console}` key prefix로 분리. `infra/shared/main.tf` backend에 하드코딩됨. | 진우 | ✅ 완료 |

> **DynamoDB 락 테이블 미사용 — S3 네이티브 락 채택 (Terraform 1.10+).**
> 백엔드 설정에 `use_lockfile = true` 추가 시 S3 버킷 자체에 잠금 파일(`.tflock`)을 저장해 동시 apply를 방지한다. 별도 DynamoDB 테이블 없이 버킷 하나로 state + 락을 모두 처리 — 부트스트랩 리소스 최소화.
>
> 버킷 이름은 전 세계 고유 — 실제 생성 시 팀 규칙에 맞게 정하고 이 표에 실제 이름을 기록한다.

---

## 3. Azure / Entra ID 초기 설정 — 🔄 진우 진행 중

> **담당 = 진우 전담**(Azure=신원의 주인, Entra CIEM 영역). Azure 포털에서 수동 설정, Terraform 미관리(project-draft 14번).
> **격리 환경:** M365 Business 체험 가입으로 `cnappagentic.onmicrosoft.com` 데모 전용 테넌트 생성 완료(2026-07-01). 실제 조직 테넌트에 결함을 심으면 안 됨(target-app-design 6번 SP 스코프 주의).
>
> **진행 순서(의존성):** ① 격리 테넌트 생성 → ② 그룹·계정·Teams 설정 → ③ App Registration(SSO) → ④ 결함용 App Reg·SP → ⑤ Federated Credential → ⑥ Defender(데모 때만). **③(SSO)은 `infra/console` apply(Cognito 연동)의 선행.**

### 3.1 테넌트 기본 정보 ✅

| 항목 | 값 |
|---|---|
| **테넌트 이름** | cnapp |
| **주 도메인** | `cnappagentic.onmicrosoft.com` |
| **테넌트 ID** | `8e160cea-faa9-47de-a717-6eb01e4a262b` |
| **라이선스** | Microsoft Entra ID Free |

### 3.2 관리자 계정 ✅

| 계정 | 역할 | 상태 |
|---|---|---|
| `jw_kim@cnappagentic.onmicrosoft.com` | Global Administrator (소유자, 진우) | ✅ |
| `jh_lee@cnappagentic.onmicrosoft.com` | Global Administrator (준형) | ✅ |

### 3.3 그룹 (보안 그룹) ✅

| 그룹 이름 | 용도 | 상태 |
|---|---|---|
| `cnapp-viewer` | 관제 앱 viewer 권한 → SAML 그룹 클레임 매핑 | ✅ |
| `cnapp-approver` | 관제 앱 approver 권한 → SAML 그룹 클레임 매핑 | ✅ |

### 3.4 데모 테스트 계정 ✅

| 계정 | 그룹 | 용도 | 상태 |
|---|---|---|---|
| `viewer@cnappagentic.onmicrosoft.com` | cnapp-viewer | SSO 데모 — viewer 권한 시연 | ✅ |
| `approver@cnappagentic.onmicrosoft.com` | cnapp-approver | SSO 데모 — approver 권한 시연 | ✅ |

### 3.5 Teams / Workflows 웹훅 ✅

| 항목 | 값 | 상태 |
|---|---|---|
| **Teams 워크스페이스** | `cnapp-agentic` | ✅ |
| **알림 채널** | `cnapp-alerts` | ✅ |
| **웹훅 URL** | `https://default8e160ceafaa947dea7176eb01e4a26.2b.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/39dbf83248914297a12849f68c1190fc/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=q2QR1HTgjZa_mo2GBEXqLJX-EGLC5a3FHBYS3E3e_Sg` | ✅ |

> ⚠️ 웹훅 URL은 민감 정보 — 실제 운용 시 Secrets Manager로 이동 권장.

### 3.6 App Registration / SP

| 항목 | 내용 | 담당 | 상태 |
|---|---|---|---|
| **② App Registration — SSO 연동용** | Cognito SAML 2.0 IdP 연동. `custom:groups` 클레임 매핑(console-app-design §7). *`infra/console` 선행.* | 진우 | 미착수 |
| **③ App Registration — 과도권한 결함용** | `Directory.ReadWrite.All` Application 권한. 골든 f8·f16 소스. | 진우 | ✅ 완료 |
| **③ Service Principal — order 평문 시크릿용** | `Directory.Read.All` + `Application.Read.All` 스코프만. 만료일 6개월. order 파드 env에 평문 노출(결함 f5). | 진우 | ✅ 완료 |
| **③ Service Principal — Prowler 스캔용** | `Directory.Read.All` + `Policy.Read.All` + `AuditLog.Read.All`. Prowler Azure 모드가 이 SP로 Entra/Defender 스캔 → OCSF → S3. | 진우 | ✅ 완료 |
| **④ Federated Identity Credential (Prowler SP)** | Prowler 스캔 SP에 GitHub Federated Credential 등록. Subject: `repo:jun0601/cnapp-agentic:ref:refs/heads/main`. 키리스 인증(D4). | 진우 | ✅ 완료 |
| **⑤ Defender for Cloud** | 데모 기간만 활성, 이후 비활성(종량제 — project-draft 22번). | 진우 | 미착수 |

#### 3.6.1 과도권한 App Registration 상세 ✅

| 항목 | 값 |
|---|---|
| **앱 이름** | `cnapp-agentic-overpriv-app` |
| **Application (client) ID** | `283ca885-134e-4a74-92d6-7dd1ed9cd46f` |
| **Tenant ID** | `8e160cea-faa9-47de-a717-6eb01e4a262b` |
| **API 권한** | `Directory.ReadWrite.All` (Application, 관리자 동의 완료) |
| **클라이언트 시크릿 만료** | 2028-07-01 (24개월) |
| **클라이언트 시크릿 값** | ⚠️ git 미기록 — 본인 로컬 보관. 실배포 시 Secrets Manager 이전 예정 |

> 이 앱 등록 자체가 CIEM finding `INTERNAL-ENTRA-OVERPRIV-APP-001`(f8)의 소스.
> 만료 없는(장기) 시크릿이 finding `INTERNAL-ENTRA-SP-CRED-001`(f16)의 소스.

#### 3.6.2 order 평문 시크릿용 SP 상세 ✅

| 항목 | 값 |
|---|---|
| **앱 이름** | `cnapp-agentic-order-sp` |
| **Application (client) ID** | `541938e7-2d6d-4098-b211-1512f3026a30` |
| **Tenant ID** | `8e160cea-faa9-47de-a717-6eb01e4a262b` |
| **API 권한** | `Directory.Read.All` + `Application.Read.All` (Application, 관리자 동의 완료) |
| **클라이언트 시크릿 만료** | 6개월 (~2027-01) |
| **클라이언트 시크릿 값** | ⚠️ git 미기록 — 본인 로컬 보관. `apps/target/order` 파드 env에 평문 노출 예정(결함 f5) |

> 이 SP 자격증명을 order 파드 매니페스트 env에 평문으로 박는 것 자체가 finding `INTERNAL-SECRET-PLAINTEXT-001`(f5) 소스.

#### 3.6.3 Prowler 스캔용 SP 상세 ✅

| 항목 | 값 |
|---|---|
| **앱 이름** | `cnapp-agentic-prowler-sp` |
| **Application (client) ID** | `82fec3e9-4c20-4d78-bf4a-9e518a86b460` |
| **Tenant ID** | `8e160cea-faa9-47de-a717-6eb01e4a262b` |
| **API 권한** | `Directory.Read.All` + `Policy.Read.All` + `AuditLog.Read.All` (Application, 관리자 동의 완료) |
| **인증 방식** | 클라이언트 시크릿 없음 — **GitHub Federated Identity Credential (키리스)** |
| **Federated Credential** | 조직 `jun0601` / 리포 `cnapp-agentic` / 브랜치 `main` / 이름 `prowler-github-oidc` |

> GitHub Actions에서 `azure/login` 액션으로 이 SP에 OIDC 인증 → 시크릿 없이 Prowler 스캔 가능.

#### 3.6.4 ⚠️ 실전환 시 맞출 것 (mock ↔ real 정합 — 지금은 정상, 나중 리마인드)

Prowler가 실제 Entra finding을 흘리기 시작하면 아래 2건을 반드시 맞춘다:

1. **mock GUID → 실 appId 스왑.** `contracts/mock-attack-paths.json`·`mock-findings.json`의 Azure 노드는 placeholder GUID(n4 `azure:service_principal:b2c3d4e5…` · n5 `azure:app_registration:a1b2c3d4…`)다. 실 finding의 `resource_id`는 위 실제 appId(`order-sp 541938e7…` · `overpriv-app 283ca885…`)를 써야 정합(4.4.1a 캐논). **실전환 전까지는 placeholder가 정상.**
2. **f16(무만료 SP cred, `INTERNAL-ENTRA-SP-CRED-001`) 노드 매핑 확인.** contracts/target-app-design §2.0은 f16 → **노드 n4(service_principal)**로 매핑. 그런데 실물에선 무만료(24개월) 시크릿을 **`overpriv-app`(App Registration, n5쪽)**에 붙였고, 실 SP인 `order-sp`엔 6개월(f5용)을 붙였다. → **f16을 n4(order-sp)에 둘지 / n5(overpriv-app)에 둘지 진우와 확정** 후 mock·카탈로그·§2.0을 일치시킨다.

---

## 4. AWS Bedrock 모델 액세스 — ✅ 완료 (담당: 준형)

> 엔진 실 tool-use(Evidence)의 LLM 호출용. **모델 액세스 페이지는 폐지(retired)** — 서버리스 파운데이션 모델은 계정에서 첫 호출 시 자동 활성화된다. 단 **Anthropic 모델은 최초 1회 use-case 상세 제출** 필요(계정당 1회). Terraform 미관리(콘솔 수동).

| 항목 | 값 |
|---|---|
| **리전** | 서울(ap-northeast-2) |
| **Anthropic use-case 제출** | ✅ 완료(2026-07-02) — 플레이그라운드에서 Claude Haiku 4.5 응답 확인 |
| **Evidence 모델 (Haiku 티어)** | `global.anthropic.claude-haiku-4-5-20251001-v1:0` (Global inference profile) |
| **Sonnet 티어(Hypothesis·Reasoning)** | 실 사용 시 동일 방법(추론 프로파일)으로 확정 |
| **인증** | 콘솔 로그인 사용자(`jh_lee`, admin) — 실 호출은 read-only 역할 + `bedrock:InvokeModel` |
| **비용 대안** | Amazon Nova Lite(A/B 비교 후보, `--model` 스왑) |

> ⚠️ **Provisioned Throughput 미사용(on-demand만)** — idle 비용 0, 종량제(토큰당). bare 모델명은 404 → 위 inference profile ID 사용. `bedrock_planner.py`의 `DEFAULT_MODEL_ID`에 반영됨.
> **남은 것(Phase1 마무리):** `infra/slice` apply + `python -m engine.run_real`로 "LLM이 실제 read-only API 자가 호출" end-to-end 검증(준형과 함께, <$1).

---

*수동 관리 리소스 현황 — Terraform 외부에서 직접 생성·설정한 항목만 기록. Terraform 관리 리소스는 `infra/` 폴더 코드가 기준.*
