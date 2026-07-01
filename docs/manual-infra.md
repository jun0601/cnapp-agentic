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
>
> *원칙: AWS 워크로드·부트스트랩은 준형 주도, Azure(신원=Entra)는 진우가 전담. 상세는 아래 각 절.*

---

## 1. AWS 계정 초기 설정 — ✅ 완료 (담당: 준형)

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
> **격리 환경 필수:** 데모용 Entra 테넌트(별도) 또는 sandbox 구독 분리 후 진행 — 실제 조직 테넌트에 결함을 심으면 안 됨(target-app-design 6번 SP 스코프 주의).
>
> **진행 순서(의존성):** ① 격리 테넌트(M365/Entra) 생성 → ② App Registration(SSO) + 그룹 → ③ 결함용 App Reg·SP(order 평문 시크릿·Prowler 스캔) → ④ Federated Credential → ⑤ Defender(데모 때만). **①이 나머지 전부의 선행**이고, ②(SSO)는 `infra/console` apply(Cognito 연동)의 선행이다.

| 항목 | 내용 | 담당 | 상태 |
|---|---|---|---|
| **① 데모 격리 환경** | 데모 전용 **M365/Entra 테넌트** 또는 sandbox 구독 분리. | 진우 | 🔄 **진행 중** |
| **② App Registration — SSO 연동용** | Cognito SAML 2.0 IdP 연동. `cnapp-viewer`·`cnapp-approver` 그룹 생성 → Cognito 토큰 `custom:groups` 클레임 매핑(console-app-design §7). *`infra/console` 선행.* | 진우 | 미착수 |
| **③ App Registration — 과도권한 결함용** | `Directory.ReadWrite.All` 등 CIEM finding 소스용(격리 테넌트에만). 골든 f8·f16. | 진우 | 미착수 |
| **③ Service Principal — order 평문 시크릿용** | `Directory.Read.All` + `Application.Read.All` 스코프만. 만료일 = 데모 종료일 +1주. order 파드 env에 평문 노출(결함 f5). | 진우 | 미착수 |
| **③ Service Principal — Prowler 스캔용** | `Security Reader` 역할 수준 read-only SP. Prowler Azure 모드가 이 SP로 Entra/Defender 스캔 → OCSF → S3 파이프라인. | 진우 | 미착수 |
| **④ Federated Identity Credential (Prowler SP)** | Prowler 스캔 SP에 GitHub 저장소를 Federated Credential로 등록. Subject: `repo:jun0601/cnapp-agentic:ref:refs/heads/main`. GitHub Actions가 client-secret 없이 Azure 인증(D4 키리스). | 진우 | 미착수 |
| **⑤ Defender for Cloud** | 데모 기간만 활성, 이후 비활성(종량제 — project-draft 22번). | 진우 | 미착수 |

---

*수동 관리 리소스 현황 — Terraform 외부에서 직접 생성·설정한 항목만 기록. Terraform 관리 리소스는 `infra/` 폴더 코드가 기준.*
