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
> | §1 AWS 계정 초기 설정 | **진우** | ✅ 완료 |
> | §2 Terraform 부트스트랩(state 버킷) | **진우** | ✅ 완료 |
> | §3 Azure / Entra ID 초기 설정 | **진우**(신원 영역 주인) | ✅ 완료 (테넌트·그룹·계정·Teams·App Reg 4종·Federated Credential. Defender는 D11로 범위 제외) |
> | §4 AWS Bedrock 모델 액세스 | **준형**(AWS·엔진 Evidence) | ✅ 완료 |
>

---

## 1. AWS 계정 초기 설정 — ✅ 완료 (담당: 진우)

> project-draft.md D1~D3(11번) 가드레일 그대로 반영. 협업자도 이 상태를 전제로 작업 시작.

| 영역 | 설정 내용 | 담당 | 상태 |
|---|---|---|---|
| **계정 기본** | 단일 계정, 콘솔 기본 리전 **서울(ap-northeast-2)**. 계정 별칭 설정 완료. Organizations/Identity Center/Control Tower **미활성 확인됨**. | 진우 | ✅ |
| **루트 계정** | MFA(가상 MFA 앱) 활성화. 액세스 키 없음(보유 시 즉시 삭제). 이후 비상용(결제 변경 등)으로만 사용. | 진우 | ✅ |
| **결제 가드레일** | IAM 사용자/역할의 결제 정보 액세스 활성화. Free Tier 알림 ON. AWS Budgets **$50/$100** 2단계 알림(임계 80%/100%, 본인+협업자 이메일). | 진우 | ✅ |
| **IAM 사용자** | `Admins` 그룹(`AdministratorAccess`) 생성. 사용자: **`jw_kim`(진우)·`jh_lee`(준형)** — 모두 그룹 소속. **각자 MFA 필수.** 장기 Access Key 미발급 원칙(CLI는 임시 자격증명만). | 진우(생성)·각자(MFA) | ✅ |
| **CloudTrail** | 멀티 리전 트레일 생성(D2 전 리전 수집). 관리 이벤트 읽기/쓰기 활성화. 암호화 SSE-S3(기본). 로그 파일 검증 ON. SNS·CloudWatch Logs 연동 OFF. | 진우 | ✅ |

> 📎 **2026-07-03 추가:** 트레일 자체는 계속 위 상태(수동 관리) 그대로 두되, `infra/monitoring`이 "트레일 → CloudWatch Logs" 배관(로그그룹 `/aws/cloudtrail/cnapp-agentic` + `cloudtrail.amazonaws.com`이 assume할 IAM 역할)을 코드로 준비해뒀다. `infra/monitoring` apply 후 출력값(`cloudtrail_log_group_arn`·`cloudtrail_cwl_role_arn`)을 CloudTrail 콘솔 → 이 트레일 편집 → "CloudWatch Logs" 섹션에 붙여넣는 **1회 수동 연결**만 남음(트레일이 Terraform state 밖이라 마지막 단계만 수동, 상세는 `infra/monitoring/README.md` §10).

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

## 3. Azure / Entra ID 초기 설정 — ✅ 완료 (담당: 진우)

> **담당 = 진우 전담**(Azure=신원의 주인, Entra CIEM 영역). Azure 포털에서 수동 설정, Terraform 미관리(project-draft 14번).
> **격리 환경:** M365 Business 체험 가입으로 `cnappagentic.onmicrosoft.com` 데모 전용 테넌트 생성 완료(2026-07-01). 실제 조직 테넌트에 결함을 심으면 안 됨(target-app-design 6번 SP 스코프 주의).
>
> **진행 순서(의존성):** ① 격리 테넌트 생성 → ② 그룹·계정·Teams 설정 → ③ App Registration(SSO) → ④ 결함용 App Reg·SP → ⑤ Federated Credential → ⑥ Defender(데모 때만). **③(SSO) ✅ 완료(2026-07-02)** — 메타데이터 URL을 `infra/console/variables.tf`의 `saml_metadata_url` 기본값으로 반영해, `infra/console` apply 선행 조건이 풀렸다(§3.6.1 상세).

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
| **웹훅 URL** | 🔴 **레닥션(2026-07-03) — 아래 참고, 로테이션 필요** | ⚠️ |

> 🔴 **보안 조치 필요(긴급):** 이 표에 실제 웹훅 URL(서명값 `sig=` 포함)이 평문으로 커밋돼 있었고, 이 레포는 **GitHub 공개(public) 저장소**로 확인됨 — 즉 지금 이 URL을 아는 누구나 우리 Teams `cnapp-alerts` 채널에 임의로 워크플로를 트리거할 수 있는 상태로 인터넷에 노출돼 있었다. 조치 순서:
> 1. **Power Automate에서 이 워크플로의 웹훅을 즉시 재생성(로테이션)** — 기존 서명(`sig=...`)은 폐기.
> 2. 새 URL은 **git에 절대 커밋하지 말고 AWS Secrets Manager**에만 저장 — 받는 자리는 이미 준비됨: `infra/monitoring`이 만드는 시크릿 `cnapp-agentic/teams/webhook`(생성만 하고 값은 Terraform이 모름, `terraform output teams_webhook_secret_arn`으로 ARN 확인 후 `aws secretsmanager put-secret-value --secret-id <ARN> --secret-string '<새 URL>'`로 1회 수동 주입).
> 3. git 히스토리에는 옛 URL이 과거 커밋에 남아있음 — 1번(로테이션)만 해도 그 값은 무력화되지만, 완전히 지우고 싶으면 `git filter-repo`/BFG로 히스토리 재작성(단 force-push라 준형과 리클론 조율 필요, 급하지 않으면 로테이션만으로 충분).
> 4. SNS→Lambda(Teams notifier)가 이 값을 쓰는 부분은 **이미 구현 완료**(`infra/monitoring/lambda_src/teams_notifier.py`, 2026-07-03) — 런타임에 Secrets Manager에서 조회하고 코드·tfvars·상태 어디에도 하드코딩 안 함. `infra/monitoring` apply 후 위 2번 값 주입만 하면 알람이 실제로 Teams에 뜬다.

### 3.6 App Registration / SP

| 항목 | 내용 | 담당 | 상태 |
|---|---|---|---|
| **③ App Registration — SSO 연동용** | Cognito SAML 2.0 IdP 연동. `custom:groups` 클레임 매핑(console-app-design §7). | 진우 | ✅ 완료 |
| **④ App Registration — 과도권한 결함용** | `Directory.ReadWrite.All` Application 권한. 골든 f8 소스. | 진우 | ✅ 완료 |
| **④ Service Principal — order 평문 시크릿용** | `Directory.Read.All` + `Application.Read.All` 스코프만. 만료일 24개월(장기 유효 — f16 소스 겸용). order 파드 env에 평문 노출(결함 f5). | 진우 | ✅ 완료 |
| **④ Service Principal — Prowler 스캔용** | `Directory.Read.All` + `Policy.Read.All` + `AuditLog.Read.All`. Prowler Azure 모드가 이 SP로 Entra/Defender 스캔 → OCSF → S3. | 진우 | ✅ 완료 |
| **⑤ Federated Identity Credential (Prowler SP)** | Prowler 스캔 SP에 GitHub Federated Credential 등록. Subject: `repo:jun0601/cnapp-agentic:ref:refs/heads/main`. 키리스 인증(D4). | 진우 | ✅ 완료 |
| **⑥ Defender for Cloud** | ~~데모 기간만 활성~~ → **시도 후 범위 제외 확정(2026-07-07, D11)** — Discovery·FoundationalCspm·CloudPosture 다 켜고 테넌트 가시성 권한까지 줬으나 Azure 실 리소스가 0개(Entra 신원 객체뿐)라 CSPM 평가 대상 자체가 없음을 실측. CloudPosture는 Free로 되돌림. 상세 `infra/monitoring/README.md` §7·`project-draft.md` D11. | 진우 | ✅ 범위 제외 |

#### 3.6.1 SSO 연동용 App Registration 상세 ✅

| 항목 | 값 |
|---|---|
| **앱 이름** | `cnapp-agentic-console-sso` (엔터프라이즈 애플리케이션, 비갤러리) |
| **Application (client) ID** | `7c37dd9a-5dc2-4f1f-9482-919fe20267b1` |
| **Tenant ID** | `8e160cea-faa9-47de-a717-6eb01e4a262b` |
| **SAML 식별자(엔터티 ID)** | `urn:amazon:cognito:sp:cnapp-agentic-demo` — ⚠️ 임시값(아래 참고) |
| **SAML 회신 URL(ACS)** | `https://cnapp-agentic-demo.auth.ap-northeast-2.amazoncognito.com/saml2/idpresponse` |
| **앱 페더레이션 메타데이터 URL** | `https://login.microsoftonline.com/8e160cea-faa9-47de-a717-6eb01e4a262b/federationmetadata/2007-06/federationmetadata.xml?appid=7c37dd9a-5dc2-4f1f-9482-919fe20267b1` — `infra/console/variables.tf`의 `saml_metadata_url` 기본값으로 반영 완료 |
| **그룹 클레임** | "보안 그룹" 모드 + 원본특성 "그룹 ID"(GUID) — 무료 티어라 "애플리케이션에 할당된 그룹"(P1/P2 필요)·"클라우드 전용 그룹 이름 내보내기"(보안 그룹 모드 미지원) 둘 다 불가 → GUID로만 나옴 |
| **사용자 할당** | 그룹 할당 불가(라이선스)라 **개별 사용자** 할당 — `viewer@`·`approver@`(데모) + **`jh_lee@`·`jw_kim@`(실사용, 2026-07-06 추가)**. jh_lee@는 `cnapp-approver` 그룹 멤버라 앱에서 APPROVER(실확인). |
| **cnapp-approver 개체 ID** | `4d6be000-2a4b-43f7-95ff-cfdb87da786d` |
| **cnapp-viewer 개체 ID** | `4d9b6544-47ea-495e-99be-8943362d6bc7` |

> 클레임에 그룹 **이름**이 아닌 **GUID**만 실리므로, `apps/console-backend/src/auth.ts`가 `cnapp-approver` 문자열이 아니라 위 **개체 ID(GUID)**로 매칭하도록 구현(이름보다 불변 식별자 매칭이 더 견고 — 의도적 설계, 임시방편 아님).

**⚠️ apply 후 확인할 것:** SAML 식별자(엔터티 ID)가 지금은 `urn:amazon:cognito:sp:cnapp-agentic-demo`(도메인 프리픽스 기반 임시값)인데, AWS Cognito의 실제 SAML SP 엔터티 ID 규칙은 보통 `urn:amazon:cognito:sp:<user_pool_id>`다. `user_pool_id`는 `infra/console` apply 후에만 발급되므로, **apply 후 실제 Cognito User Pool ID로 Entra 앱의 "식별자" 필드를 다시 확인/수정**해야 SSO 로그인이 실제로 성공한다(§3.6.5에 추가 리마인더).

#### 3.6.2 과도권한 App Registration 상세 ✅

| 항목 | 값 |
|---|---|
| **앱 이름** | `cnapp-agentic-overpriv-app` |
| **Application (client) ID** | `283ca885-134e-4a74-92d6-7dd1ed9cd46f` |
| **Tenant ID** | `8e160cea-faa9-47de-a717-6eb01e4a262b` |
| **API 권한** | `Directory.ReadWrite.All` (Application, 관리자 동의 완료) |
| **클라이언트 시크릿 만료** | 2028-07-01 (24개월) |
| **클라이언트 시크릿 값** | ⚠️ git 미기록 — 본인 로컬 보관. 실배포 시 Secrets Manager 이전 예정 |

> 이 앱 등록 자체가 CIEM finding `INTERNAL-ENTRA-OVERPRIV-APP-001`(f8)의 소스.

#### 3.6.3 order 평문 시크릿용 SP 상세 ✅

| 항목 | 값 |
|---|---|
| **앱 이름** | `cnapp-agentic-order-sp` |
| **Application (client) ID** | `541938e7-2d6d-4098-b211-1512f3026a30` |
| **Tenant ID** | `8e160cea-faa9-47de-a717-6eb01e4a262b` |
| **API 권한** | `Directory.Read.All` + `Application.Read.All` (Application, 관리자 동의 완료) |
| **클라이언트 시크릿 만료** | 24개월(2028-07-01) — 비밀 ID `e0589f10-3ad7-4975-81c3-a21f324d1e14` |
| **클라이언트 시크릿 값** | ⚠️ git 미기록 — 본인 로컬 보관. `apps/target/order` 파드 env에 평문 노출 예정(결함 f5) |

> 이 SP 자격증명을 order 파드 매니페스트 env에 평문으로 박는 것 자체가 finding `INTERNAL-SECRET-PLAINTEXT-001`(f5) 소스.
> **장기(24개월) 유효 시크릿 자체가 finding `INTERNAL-ENTRA-SP-CRED-001`(f16)의 소스** — 2026-07-02 §3.6.5 리마인더 해소 시 6개월→24개월로 재발급(기존 시크릿 `acbe478f-...` 삭제). Entra가 포털 레벨에서 "무만료" 옵션 자체를 지원 안 해 최대치(24개월/730일)로 설정 — control 타이틀도 "무만료"가 아닌 "장기 유효(6개월 초과)"로 완화.

#### 3.6.4 Prowler 스캔용 SP 상세 ✅

| 항목 | 값 |
|---|---|
| **앱 이름** | `cnapp-agentic-prowler-sp` |
| **Application (client) ID** | `82fec3e9-4c20-4d78-bf4a-9e518a86b460` |
| **Tenant ID** | `8e160cea-faa9-47de-a717-6eb01e4a262b` |
| **API 권한** | `Directory.Read.All` + `Policy.Read.All` + `AuditLog.Read.All` (Application, 관리자 동의 완료) |
| **인증 방식** | 클라이언트 시크릿 없음 — **GitHub Federated Identity Credential (키리스)** |
| **Federated Credential** | 조직 `jun0601` / 리포 `cnapp-agentic` / 브랜치 `main` / 이름 `prowler-github-oidc` |
| **구독 Reader 역할 (2026-07-08 추가)** | 구독 `c7fd722a-…` 범위에 **Reader** 역할 부여 완료(SP objectId `ce887263-…`) — 이게 있어야 `prowler azure`가 구독을 열거·스캔할 수 있음. |

> GitHub Actions에서 `azure/login` 액션으로 이 SP에 OIDC 인증 → 시크릿 없이 Prowler 스캔 가능.
>
> **⚠️ 구독 Reader 역할 부여 방법 (2026-07-08 실측 — 재구축 시 필수):** `az role assignment create`/`list`가 이 구독에서 `MissingSubscription`으로 깨진다(az CLI 래퍼 버그 — 구독 자체는 정상). **`az rest`(raw ARM REST API)로 우회**해야 함:
> ```bash
> AID=$(python -c "import uuid;print(uuid.uuid4())")
> az rest --method PUT \
>   --uri "https://management.azure.com/subscriptions/c7fd722a-c106-4eff-a64d-88b36dcee28a/providers/Microsoft.Authorization/roleAssignments/${AID}?api-version=2022-04-01" \
>   --body '{"properties":{"roleDefinitionId":"/subscriptions/c7fd722a-c106-4eff-a64d-88b36dcee28a/providers/Microsoft.Authorization/roleDefinitions/acdd72a7-3385-48ef-bd42-f606fba81ae7","principalId":"ce887263-ff39-45a9-a6da-fc10850a5b56","principalType":"ServicePrincipal"}}'
> ```
> (`acdd72a7-…`=Reader 내장 역할 ID, `ce887263-…`=prowler-sp의 SP objectId. 조회도 `az rest --method GET`으로.) 이걸 부여하기 전엔 Prowler azure가 "It was not possible to retrieve any subscriptions"로 죽는다. 부여 후 prowler-scan 워크플로가 AWS와 동일하게 S3→ingest→normalize→RDS 완주함(실측 확인).

#### 3.6.5 ⚠️ 실전환 시 맞출 것 (mock ↔ real 정합 — 지금은 정상, 나중 리마인드)

Prowler가 실제 Entra finding을 흘리기 시작하면 아래를 반드시 맞춘다:

1. **mock GUID → 실 appId 스왑.** `contracts/mock-attack-paths.json`·`mock-findings.json`의 Azure 노드는 placeholder GUID(n4 `azure:service_principal:b2c3d4e5…` · n5 `azure:app_registration:a1b2c3d4…`)다. 실 finding의 `resource_id`는 위 실제 appId(`order-sp 541938e7…` · `overpriv-app 283ca885…`)를 써야 정합(4.4.1a 캐논). **실전환 전까지는 placeholder가 정상.**

**[x] f16 노드 매핑 확정(2026-07-02, 준형↔진우 확정) — closed.** `attackpath/correlation.py`의 R3 규칙이 `INTERNAL-ENTRA-SP-CRED-001` control_id를 가진 finding을 **코드로 n4에 고정**해서 배정한다(`_R3_AZURE_SP` → `Node("n4", ...)`). 이 control_id를 다른 노드로 옮기면 그래프가 깨지므로(n4/n5 resource_id 충돌), **f16 = n4(order-sp) 고정**으로 확정 — mock/contracts 변경 없음. 대신 실물 쪽을 맞춤: order-sp 시크릿을 6개월→**24개월(2028-07-01, 비밀 ID `e0589f10-3ad7-4975-81c3-a21f324d1e14`)로 재발급**(§3.6.3). Entra가 포털에서 "무만료" 옵션을 아예 제공하지 않아(플랫폼 보안 기본값 — 최대 730일/24개월) control 타이틀도 "무만료" 대신 **"장기 유효(6개월 초과)"**로 완화(control-catalog.json·mock-findings.json·target-app-design §2.0 반영). overpriv-app(§3.6.2)은 f8만 소스, f16과 무관으로 정정.

2. **[x] SSO SAML 식별자(엔터티 ID) — 라이브 반영됨(반복 절차).** Entra `cnapp-agentic-console-sso`의 SAML 식별자를 실 Cognito Pool ID(`urn:amazon:cognito:sp:<user_pool_id>`)로 맞춰야 SSO 로그인 성공. 현재 라이브(`ap-northeast-2_Mp3cVlIKs`)로 맞춰져 실 로그인 확인됨. ⚠️ **console을 destroy→재apply할 때마다 Pool ID가 새로 발급되므로 그때마다 재갱신 필요** — 상세·최신 이력은 §5(4)번 참고.

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
> ✅ **Phase1 end-to-end 검증 완료(2026-07-02):** `infra/slice` apply → `python -m engine.run_real` → destroy 실행. 실 Bedrock Haiku가 실 S3를 read-only 자가 조사 → CONFIRMED. slice 버킷은 검증 후 destroy(상시 미유지 — 재검증 시 재-apply). 비용 실측 ~$0.

---

## 5. 도메인 + SSO 활성 (관제 앱) — ✅ 완료·실 SSO 로그인 검증(2026-07-06) (담당: 준형 배선 / 도메인 구매·NS: 진우)

> 관제 앱(console)에 커스텀 도메인을 붙이고 실제 SSO 로그인을 켜는 절차. **구조 결정(2026-07-03) = 옵션 B: SPA가 Cognito Hosted UI로 직접 OIDC 로그인**(프론트→Cognito→Entra SAML→역할 표시). 기존 ALB authenticate-cognito는 이 방식엔 미사용(ALB는 API 백엔드로만).

### 5.1 도메인
| 항목 | 값 |
|---|---|
| **도메인** | `cnapp-agentic.cloud` (가비아 구매, 2026-07-03) — 관제 앱 전용 |
| **용도** | CloudFront(SPA 프론트) apex. Cognito Hosted UI는 Cognito 기본 도메인 사용(커스텀 불요) |

### 5.2 Route53 호스팅 영역 — ⚠️ 영구 유지 (destroy 금지)
| 항목 | 값 |
|---|---|
| **Zone ID** | `Z063995231WAW63UT354D` (AWS CLI로 생성, 2026-07-03) |
| **⚠️ 규칙** | **삭제·재생성 금지** — 삭제하면 네임서버가 바뀌어 가비아에 다시 넣어야 함. EKS 스택을 destroy해도 이 호스팅 영역은 유지(terraform 밖, CLI 관리). |
| **네임서버(가비아 위임값)** | `ns-865.awsdns-44.net` · `ns-1221.awsdns-24.org` · `ns-279.awsdns-34.com` · `ns-1812.awsdns-34.co.uk` |

### 5.3 네임서버 위임 (수동 1회) — ✅ 입력 완료 (진우, 2026-07-03)
가비아 → 타 기관 네임서버 → 위 4개 입력. **DNS 전파 대기 중**(보통 15분~2시간). 확인: `nslookup -type=NS cnapp-agentic.cloud 8.8.8.8`가 awsdns를 반환하면 위임 완료.

### 5.4 SSO 활성 절차 (✅ 완료·라이브 검증 — 기록)
1. **DNS 위임 확인:** `nslookup -type=NS cnapp-agentic.cloud 8.8.8.8` → awsdns 4개 나오면 OK.
2. **console apply(도메인 켜기):** `cd infra/console && terraform apply -var enable_custom_domain=true` → domain-sso.tf가 ACM 인증서(us-east-1) 발급·DNS 자동검증 → CloudFront 커스텀 도메인 연결 → SPA용 Cognito 앱 클라이언트(public/PKCE) 생성. (`terraform output spa_cognito_client_id`·`cognito_hosted_ui_domain` 확보)
3. **✅ 프론트 OIDC 배선 (구현 완료 — `apps/console/src/lib/oidc.ts`):** Login 버튼→Cognito Hosted UI authorize redirect(PKCE, 외부 라이브러리 없이 Web Crypto), `/callback` 라우트에서 code→token 교환, ID토큰 `custom:groups`(GUID)→viewer/approver. **재apply 때 할 일은 코드 작성이 아니라 값 주입뿐** — `apps/console/.env.production.local`에 `VITE_COGNITO_CLIENT_ID`(새 SPA client)·`VITE_COGNITO_DOMAIN`·`VITE_REDIRECT_URI` 넣고 재빌드→S3 업로드→CloudFront 무효화.
4. **✅ Entra 엔티티 ID(§3.6.5) — Pool ID는 재apply마다 바뀜:** Entra `cnapp-agentic-console-sso` 앱 SAML 식별자를 **현 라이브 Cognito Pool**로 교체해야 로그인됨(안 맞으면 `AADSTS700016: Application with identifier … not found`). 이력: `_axVuh328G`(2026-07-06) → `_g7Q21LGFJ`(2026-07-07) → `_Mp3cVlIKs`(2026-07-08) → `_a4N8fqDUE`(2026-07-13) → **`urn:amazon:cognito:sp:ap-northeast-2_oPh5Bb6qn`**(2026-07-21 현재 라이브). (회신 URL `https://cnapp-agentic-demo.auth.ap-northeast-2.amazoncognito.com/saml2/idpresponse`는 도메인 프리픽스 기반이라 불변.) ⚠️ **console을 destroy→재apply할 때마다 Pool ID 새로 발급** → `terraform -chdir=infra/console output cognito_user_pool_id`로 확인 후 Entra 식별자 재갱신. SSO 자주 켤 거면 console 레이어 유지 권장.
5. **✅ 실사용 계정 SSO 활성(2026-07-06):** Enterprise App `cnapp-agentic-console-sso`에 **jh_lee@·jw_kim@ 개별 할당** + **jh_lee@ → `cnapp-approver`(4d6be000-…) 그룹 멤버 추가** → 앱에서 **APPROVER 실확인**. jw_kim@ 역할은 필요 시 cnapp-viewer/approver 그룹에 추가(미지정=기본 viewer). 기존 데모 계정 `viewer@`·`approver@`도 그대로 유효. **역할=Entra 보안 그룹 멤버십**("역할 및 관리자"의 Entra 관리자 역할과 무관 — 그건 글로벌 관리자 등 테넌트 권한).
6. **✅ 검증(2026-07-06):** 시크릿창 → `https://cnapp-agentic.cloud` → 로그인 → `jh_lee@cnappagentic.onmicrosoft.com` → Cognito→Entra(SAML)→`/callback` → 대시보드 **실데이터 20건(Critical 5·크로스클라우드 attack-path) + 우상단 APPROVER** 표시. **SSO+RBAC+실데이터 end-to-end 라이브 확인.** (역할 판정은 console-backend Lambda가 Cognito JWKS로 JWT 검증 후 custom:groups GUID로 — 위조 불가, 보안 하드닝 #3.)

> **상태(2026-07-21 기준):** 도메인·ACM·CloudFront·SPA OIDC·Cognito SAML·Entra 앱 할당·그룹 전부 라이브. 유일한 유지보수 포인트 = console를 destroy→재apply하면 Cognito Pool ID가 바뀌므로 Entra 앱 SAML 식별자 재갱신 필요(§5.4 #4, 현 Pool `ap-northeast-2_oPh5Bb6qn`(2026-07-21 재apply) · SPA client `556scn7abrqilgib0mrg7psb61` — ⚠️ **Entra 식별자 갱신은 준형 수동 대기 중**).
>
> **ArgoCD/타깃 앱 부트스트랩(2026-07-07 최초 손 실행):** `kubectl apply -n argocd --server-side -f <argocd install.yaml>`(install.yaml이 커서 server-side 필수) → `kubectl apply -f gitops/argocd/app-target.yaml` → member/product/order 자동 배포. 타깃 앱 **이미지는 GitHub Actions `build-images.yml`(Actions 탭 → Run workflow)로 ECR push** 후 파드가 pull. ArgoCD UI = `kubectl port-forward svc/argocd-server -n argocd 8080:443`(admin 비번은 `argocd-initial-admin-secret`). 상세 = `gitops/README.md` 부트스트랩 순서.

---

*수동 관리 리소스 현황 — Terraform 외부에서 직접 생성·설정한 항목만 기록. Terraform 관리 리소스는 `infra/` 폴더 코드가 기준.*
