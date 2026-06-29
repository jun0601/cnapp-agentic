# Multi-Cloud CNAPP with Agentic AI — 프로젝트 설계서 (v5)

> 상태: 방향·범위·분담·앱·멀티클라우드 확정 / 구현 진입 직전
> 성격: 2인 협업 개인 프로젝트(작업 분담, 각자 전체 이해) · 클라우드 보안 엔지니어 포트폴리오
> 한 줄: **AWS는 워크로드의 주인, Azure는 신원·데이터의 주인** — 분산된 멀티클라우드 환경을 하나의 에이전틱 CNAPP으로 점검·통합·자동 개선.

---

## 1. 한 줄 정체성

멀티 클라우드(AWS 메인 + Azure) 환경에서 **클라우드 설정(Posture)부터 워크로드·IaC 코드까지 "code-to-cloud" 보안 위험을 점검·통합**하고, 권한(CIEM)·취약점·데이터 노출을 **attack-path로 상관분석**하며, 그 위에 **에이전틱 AI(Bedrock 멀티에이전트 + RAG)**로 발견 항목을 설명·우선순위화·자동 개선하는 **CNAPP형 보안 플랫폼**.

---

## 2. 왜 이 주제인가 (객관적 근거)

### 2.1 산업 문제
- 클라우드 침해의 대부분은 정교한 해킹이 아니라 **설정 오류(misconfiguration)**에서 나온다(공개 버킷, 열린 SG, 과도 권한).
- 2026년 CNAPP의 무게중심은 "설정만 보던 것"에서 **"설정 + 워크로드 + 코드(IaC)를 하나의 그래프로 연결"**해, 단일 도구로 못 잡는 **독성 조합(toxic combination)** — 공개 버킷 + 민감 데이터 + 과도 권한 + 취약 워크로드 = 탈취 경로 — 을 잡는 방향으로 이동했다.
- 발견 항목은 수백 건씩 쏟아지는데 **무엇을 먼저 고칠지** 판단이 어렵다.
- → 규칙 나열이 아니라 **"추론으로 위험을 설명·우선순위화하고 안전하게 개선"**하는 시스템이 필요하다.

### 2.2 멀티클라우드가 현실인 이유
- 기업은 클라우드별 강점에 따라 워크로드를 **분산**한다: 컨테이너·클라우드 네이티브 워크로드는 AWS, 신원·협업(Microsoft 365 → Entra ID)·데이터 분석은 Azure.
- 보안 상태가 **여러 콘솔에 흩어져** 전체 위험 경로가 안 보인다 → 단일 뷰 통합 + 크로스클라우드 attack-path 추적이 핵심 가치.

### 2.3 시장 정렬
- 국내 주요 MSP의 핵심 사업과 직접 매핑: 멀티클라우드 CSPM·CNAPP, AI 네이티브 보안, attack-path 분석, 컴플라이언스(ISMS-P/CSAP).

---

## 3. 방향: CSPM → CNAPP 심화 (SOC 아님)

CSPM을 **넓히지 않고 깊게** 심화하되, **SOC(실시간 위협탐지/대응)가 아니라 workload(코드 방향)로** 깊이를 더한다.

- **SOC 제외 이유:** (a) 진짜 공격 데이터 확보가 어렵고 (b) 자율 대응의 안전성 리스크가 크며 (c) 초점이 흐려진다. → **확장 방향(섹션 18)으로만, 끼울 자리는 비워둠.**
- **workload 심화 이유:** CWPP·KSPM·취약점·IaC 보안은 실제 리소스를 스캔하면 데이터가 바로 나오고, EKS·IaC·CI/CD 역량에 정통으로 꽂힌다.

---

## 4. 작업 분담 (효율용 트랙)

> **원칙:** 다른 환경에서 병렬 작업하기 위해 일을 나누되, **둘 다 상대 영역까지 완전히 이해**한다. 분담은 효율 수단이지 분리 소유가 아니다.

| 트랙 | 트랙 1 | 트랙 2 |
|---|---|---|
| 새 역량 | **CI/CD · GitOps · Shift-Left** | **관측 · Grafana · 로그 파이프라인** |
| 보안 영역 | CSPM 본체 + Shift-Left CI 게이트 | 워크로드(취약점·KSPM) + CIEM + attack-path 그래프 |
| 핵심 기술 | GitHub Actions·OIDC·ArgoCD, Checkov/Trivy(CI), Config·Security Hub CSPM·Prowler | Inspector·Trivy(런타임)·kube-bench, IAM Access Analyzer, kube-prometheus-stack·로그 |

**공유 자산:** 수집 파이프라인(EventBridge→SQS→Lambda, OCSF 정규화), 에이전틱 엔진 코어, 인프라 골격(계정·IaC·EKS·인증), 관제 대시보드.

---

## 5. HALO 레퍼런스 모델 & 차별점

레퍼런스(메가존 HALO) 대비 차별점:
1. **멀티클라우드 1급** — AWS+Azure를 OCSF로 통합(이질적 보안 데이터 단일 뷰).
2. **한국 규제 네이티브** — ISMS-P/CSAP 매핑 내장.
3. **에이전틱 자율 조사 루프** — 가설→증거→판정.
4. **오픈소스 스택 투명성** — Prowler/Trivy/Checkov/kube-bench 재현 가능.
5. **Code-to-Cloud** — IaC(빌드) → CI 게이트(배포) → 설정(런타임)까지 Shift-Left + 공급망.

| HALO 구성 | 우리 대응 | 채택 |
|---|---|---|
| A&R (설정·권한·데이터 점검+개선) | CNAPP 본체 + remediation | ✅ 핵심 |
| NOVA (보안 단일 화면 통합) | 통합 관제 대시보드 | ✅ 핵심 |
| AI 보안 거버넌스 | 에이전틱 엔진 + OWASP-LLM 가드레일 | ✅ 핵심 |
| 워크로드·공급망(HALO 약점) | Shift-Left·KSPM·SBOM·서명 | ✅ 차별점 |
| AI 보안관제(SOC)·CWPP 런타임 | 위협탐지·런타임 | ⚠️ 확장만 |

---

## 6. 멀티클라우드 구도 — AWS(워크로드) / Azure(신원·데이터)

### 6.1 시나리오 (강점 기반)
> 고객사 커머스는 **워크로드는 AWS**(컨테이너·클라우드 네이티브 강점), **신원·인증은 Azure Entra ID**(Microsoft 365 생태계), **데이터 분석·민감데이터 보관은 Azure**에 둔다. 우리 CNAPP은 이 분산 환경을 한 화면에서 점검하고, **AWS 침해가 Azure 신원·데이터로 번지는 크로스클라우드 공격 경로**까지 추적한다.

이 분업 덕에 (a) "왜 Azure?"가 자연스럽고(Microsoft 365 = 신원이 Azure), (b) SSO가 곁다리가 아니라 시나리오 중심축이 되며, (c) Entra 자체를 CIEM으로 점검하는 것도 정당해진다.

### 6.2 비중
| 구분 | AWS (워크로드 주인) | Azure (신원·데이터 주인) |
|---|---|---|
| 정체성 | 컨테이너 워크로드 운영 | Microsoft 생태계 신원 + 데이터/분석 |
| 점검 깊이 | 풀 CNAPP 6기둥 | secure score + 미스컨피그 5~6개 + Entra CIEM |
| 비중 | 80% | 20% |

> Azure를 AWS와 대칭으로 만들지 않는다(과함). "의미 있는 조연" 수준 — 미끼가 아니라 시스템의 진짜 일부(신원·데이터).

---

## 7. CNAPP 기둥 + attack-path

| 기둥 | 내용 | 핵심 서비스 | 티어 |
|---|---|---|---|
| **CSPM** (설정 자세) | 설정 위반·드리프트·컴플라이언스 | Config, Security Hub CSPM, Prowler | 핵심 |
| **CIEM** (권한) | 과도/미사용 권한·상승 경로 (AWS+Entra) | IAM Access Analyzer, Entra | 핵심 |
| **취약점 관리** | 이미지·워크로드 CVE, KEV 우선순위 | Inspector, Trivy | 핵심 |
| **KSPM** (쿠버네티스 자세) | K8s 설정·Pod Security·RBAC | kube-bench(CIS K8s) | 핵심 |
| **데이터 보안(DSPM 맛)** | 민감데이터 위치·노출 (AWS+Azure) | Macie, Azure Storage 점검 | 강추 |
| **attack-path** (상관) | 위 기둥 묶어 탈취 경로(크로스클라우드 포함) | 새 Security Hub(exposure) + 커스텀 그래프 | 핵심 |
| **CWPP** (런타임) | 런타임 위협·이상행위 | GuardDuty Runtime / Falco | 확장(훅만) |

> CWPP 런타임은 SOC 경계·범위·가성비 이유로 배제하되, OCSF 스키마·대시보드에 "runtime" 자리만 비워둬 추후 입력 연결 시 반나절~하루에 추가 가능.

---

## 8. 애플리케이션 구조 (앱 2개)

### 8.1 타깃 앱 (고객사 워크로드 — 점검 대상)
- **역할:** 일부러 취약하게 설정된 고객사 시스템. findings 소스.
- **AWS:** 커머스 마이크로서비스 3~4개(상품·주문·회원·결제) + EKS.
- **Azure:** 회원 민감데이터 보관 Storage(분석용) + (선택)소형 보조 워크로드.
- **원칙:** 기능은 평범, **취약점은 IaC에 심음**(코드 버그 아님). Bedrock·SSO 없음.

### 8.2 관제 앱 (우리 플랫폼 — HALO 같은 메인 앱)
- **역할:** posture·findings·attack-path를 보여주는 얼굴. NOVA 대응.
- **화면:** 보안점수(AWS+Azure secure score 나란히), finding 목록(6종), attack-path 그래프, 각 finding의 AI 설명·조치안.
- **여기에 Bedrock·SSO가 들어감.**

### 8.3 관제 앱이 점검하는 것
고객사 앱의 *코드가 아니라 그 앱이 깔린 클라우드 환경*:
CSPM(S3·SG·IAM·암호화) · CIEM(과도 권한) · 취약점(이미지 CVE) · KSPM(Pod Security·RBAC) · 데이터(민감데이터 노출) · attack-path(크로스클라우드 탈취 경로).

### 8.4 연결 구조 (★ agentless — 직접 API 아님)
관제 앱과 타깃 앱은 **직접 통신하지 않는다.** CSPM은 agentless — 앱에 아무것도 안 심고, 클라우드 계정을 바깥에서 read-only로 스캔한다.
- 타깃 앱 → AWS/Azure 계정에 **배포**될 뿐(자기가 점검당하는지 모름).
- 스캐너(Config·Prowler·Inspector·Trivy·kube-bench·Macie·Defender) → 계정을 **read-only 스캔** → findings.
- findings → EventBridge→SQS→Lambda → OCSF 정규화 → 벡터DB/엔진 → **관제 앱이 findings 저장소를 읽어 표시.**
- **API가 있는 곳:** ① 스캐너↔클라우드 API(계정 읽기) ② 관제 앱 프론트↔우리 백엔드. **타깃 앱과의 직접 API는 없음.**
- 이 구조라서 타깃 앱이 무엇이든 무관(가져다 써도 됨). 상세는 별도 `target-app-design.md` 5번.

---

## 9. Bedrock 활용 (관제 앱 — 챗봇 아님)

> 사용자가 질문해야 답하는 챗봇이 아니라, **에이전트가 능동적으로 일하는** 방식.
> **챗봇 탈출의 단일 기준 = LLM이 read-only API를 스스로 호출해 증거를 모으는가(tool use).** #1~#5는 "주어진 finding을 가공"하는 일이라 챗봇도 할 수 있다. #0(Evidence 능동 수집)이 있어야 "진짜 에이전트"다.

| # | 유스케이스 | 내용 | 비고 |
|---|---|---|---|
| **0** | **Evidence 능동 수집 (tool use)** | Triage가 finding을 넘기면 LLM이 **추가로 무엇을 봐야 할지 스스로 판단**해 read-only API 호출(`getBucketPolicy`·`getBucketAcl`·Macie 분류 결과·IAM 정책 조회 등)로 검증·보강. #3 attack-path 상관의 입력. | **★ 챗봇 탈출 최소조건** (15번 Evidence 에이전트와 직결) |
| 1 | **자동 생성 리포트** | finding 들어오면 알아서 "왜 위험한지+근거(CIS/KEV)+조치법" 카드 생성 (RAG 핵심) | ✅ MVP |
| 2 | **우선순위 자동 정렬** | attack-path·KEV·데이터 민감도 종합해 "오늘 이거부터" 추론 정렬 | ✅ MVP |
| 3 | **attack-path 내러티브** | 그래프를 "공격자가 ~로 들어와 ~를 타고 ~를 탈취" 스토리로 서술 | 차별화 |
| 4 | **조치 코드 생성(Fix)** | 수정 Terraform/K8s/CLI 생성 → 승인 후 적용(가드레일) | 보너스 |
| 5 | **컴플라이언스 리포트** | ISMS-P 미준수 + 권고 자동 작성 | 보너스 |

> **#0과 안전 원칙:** Evidence 수집은 **read-only API만** 호출 → 거버넌스(17번)의 "Read-only first"와 정확히 부합. 변경(#4)은 휴먼인더루프 뒤에만. "read-only로 자율 조사, 변경만 승인"이 핵심 서사.
> **MVP 순서 주의:** #0은 절대사수 MVP(#1·#2)보다 뒤에 둘 수 있으나, **"에이전트라 부르려면 반드시 구현"하는 최소조건**으로 명시. 데모 전까지 #0이 한 경로라도 돌아야 한다.
> 자연어 질의창은 메인이 아니라 보조(한 귀퉁이)로만 둠.

---

## 10. SSO (앱 → Cognito → Entra ID)

```
사용자 → 관제 앱 접속
  → ALB(authenticate-oidc)가 미인증이면 Cognito로 리다이렉트
  → Cognito가 Entra ID로 페더레이션 (Entra = IdP)
  → Entra 로그인 성공 → Cognito 토큰 발급 → 관제 앱 진입
  → (앱 → AWS 리소스) Cognito Identity Pool → 임시 AWS 자격증명
```

- **역할:** Entra ID = IdP(신원), Cognito = SP/허브(AWS), 관제 앱 = Cognito 신뢰.
- **무료 가능 근거:** 기본 SAML SSO는 Entra 전 티어 무료(커스텀 앱 포함, 앱 1개 = 무료 10개 한도 내). 조건부 액세스·그룹 프로비저닝 등 P1/P2 기능 미사용. SP-initiated 흐름이라 보안 권장 방식과도 일치.
- **검증:** Week 1에 실제 테넌트로 SSO 우선 검증(이론상 무료지만 테넌트 상태 직접 확인).
- **구현:** ALB `authenticate-oidc`로 앱 코드에 인증 로직 최소화.

---

## 11. 핵심 설계 결정

### 기반
| # | 결정 | 왜 |
|---|---|---|
| D1 | 새 계정 + **단일 계정**(Organizations 미사용) | 무료 플랜에서 Organizations 켜면 유료 전환·크레딧 소멸. |
| D2 | **단일 리전(서울)** + CloudTrail/Config **전 리전 수집** | 비용↓, 단 리전 드리프트 탐지는 전 리전. |
| D3 | **IAM 어드민 + MFA, 루트 잠금**(Identity Center 미사용) | Identity Center는 Organizations 동반 → 크레딧 소멸 회피. |
| D4 | CI/CD **GitHub OIDC → IAM Role**(키 없음) | 장기 자격증명 미사용 2026 표준. |
| D5 | 파드 **IRSA / Pod Identity** | 스코프된 임시 자격증명. |
| D6 | **EKS + ArgoCD GitOps** | 배포·CI/CD 목표 핵심. |
| D7 | **앱 2개**(취약 타깃 + 관제 대시보드) | findings 소스 + NOVA 대응. |
| D8 | **취약점은 IaC에 심음** | 설정 검사 대상. 앱 부담 최소. |
| D9 | **Bedrock + 수동 RAG**(SageMaker 미사용) | ML 오버·비용 회피, 직접 조립로 깊이. |
| D10 | **앱 SSO는 Cognito**(Entra→Cognito→OIDC) | 워크포스 SSO 크레딧 문제 회피 + 멀티클라우드 신원. |
| D11 | **Azure는 Defender for Cloud로 점검** | Security Hub는 AWS 전용. |
| D12 | **Prowler 병행** | 오픈소스 멀티클라우드 스캐너. |
| D13 | **에이전틱 엔진 = 멀티에이전트** | 가설→증거→추론 루프. |

### 워크로드·Shift-Left (티어링)
| # | 결정 | 티어 |
|---|---|---|
| D14 | 취약점 스캔 빌드 단계로(CI Trivy + 런타임 Inspector) | 핵심 |
| D15 | CI 게이트(Checkov/OPA로 미스컨피그 IaC 머지 전 차단) | 핵심 |
| D16 | KSPM(kube-bench로 CIS K8s 점검) | 핵심 |
| D17 | 공급망(cosign 서명 + SBOM, ArgoCD 미서명 거부) | 보너스 |
| D18 | CWPP 런타임 배제(훅만) | 확장 |
| D19 | 공유 엔진 코어 + 도메인 로직 분리 | 핵심 |

---

## 12. 아키텍처

```
[입력: CNAPP 신호]
  AWS 설정:   Config · Security Hub CSPM · Prowler · Macie
  AWS 워크로드: Inspector · Trivy · kube-bench(KSPM) · IAM Access Analyzer(CIEM)
  AWS 빌드게이트: CI에서 Checkov/OPA(IaC) · Trivy(이미지)
  Azure:      Defender for Cloud(secure score) · Entra ID(CIEM) · Storage 점검
  [확장 훅]    CWPP 런타임 자리 (GuardDuty Runtime / Falco)
            │ (ASFF / OCSF 정규화) ※ 공유 파이프라인
            ▼
  EventBridge → SQS → Lambda
            │
┌──────── 공유 에이전틱 엔진 (Bedrock 멀티에이전트) ────────┐
│  Orchestrator → Triage → Hypothesis → Evidence → Reasoning │
│  Governance: 최소권한·read-only first·불변 감사로그·OWASP-LLM 가드레일 │
└───────────────────────────────────────────────────────────┘
            │
   [attack-path 그래프] 권한+취약점+설정+데이터 → 탈취 경로(크로스클라우드)
            │
   위반/위험 → 자동 개선 제안 → 휴먼인더루프(승인) → Step Functions → 불변 감사로그(S3 Object Lock)
            │
[관제 앱]  posture 점수(AWS+Azure) + findings + attack-path + AI 설명/조치 (React, S3+CloudFront)
[타깃 앱]  AWS 커머스(EKS) + Azure 민감데이터 Storage ← findings 소스
[CI 게이트] GitHub Actions(OIDC) → Checkov/Trivy → (cosign*) → ECR → ArgoCD → EKS
[인증]     Entra ID ─SAML─▶ Cognito ─OIDC─▶ ALB(authenticate-oidc) → 관제 앱
[관측]     kube-prometheus-stack + 로그 파이프라인
```

---

## 13. 서비스 구성 — AWS

| 티어 | 서비스 | 역할 |
|---|---|---|
| 필수 | CloudTrail | 감사 로그 토대 |
| | AWS Config | 설정 기록·규칙(CSPM 백본) |
| | Security Hub CSPM | CIS/FSBP 점검·점수 |
| | 새 Security Hub | 상관·exposure·attack-path |
| | Prowler | 오픈소스 CSPM 스캐너 |
| | IAM Access Analyzer | CIEM(권한·상승 경로) |
| | Inspector | 취약점(ECR·워크로드) |
| | Trivy | CI 이미지/IaC 취약점(오픈소스) |
| | Checkov / OPA | IaC Policy-as-Code 게이트 |
| | kube-bench | KSPM(CIS K8s) |
| | EventBridge+SQS+Lambda | 수집·정규화 |
| | Bedrock + 벡터DB | 에이전틱 RAG(OpenSearch Serverless / pgvector) |
| | Step Functions | 승인 포함 조치 |
| | EKS + ECR + ArgoCD | 워크로드·배포·GitOps |
| | Cognito | 앱 SSO 허브(SP) |
| 강추 | Macie | 데이터 보안(S3 민감데이터) |
| | Secrets Manager + KMS | 시크릿·암호화 |
| | CloudFront + S3 | 관제 앱 정적 호스팅 |
| 보너스 | cosign / Syft | 이미지 서명·SBOM |
| 선택 | SNS / Teams 웹훅 | 알림 |
| 확장 | GuardDuty (Runtime) | attack-path 보조 / CWPP 훅 |

---

## 14. 서비스 구성 — Azure

| 티어 | 서비스 | 역할 | 비고 |
|---|---|---|---|
| 필수 | Microsoft Entra ID | 신원·인증(SSO IdP) + CIEM 점검 대상 | 무료 티어. 회사 디렉터리 |
| | Defender for Cloud | Azure CSPM — secure score·권고·컴플라이언스 | AWS Security Hub 대응 |
| | Storage Account (Blob) | 고객 민감데이터 보관(분석용) | 크로스클라우드 attack-path 종착지 |
| 강추 | App Registration | SSO 연동 + 과도권한 CIEM 점검 | 어차피 SSO로 생성 |
| | Azure Policy | 리소스 규정 준수 평가 | Defender 연계, 컴플라이언스 매핑 |
| 선택 | Log Analytics Workspace | Defender 로그 수집·쿼리 | findings 파이프라인 연동 시 |
| | 소형 컨테이너 / App Service | 분석·리포팅 보조 워크로드 | 부담되면 생략(Storage만으로 성립) |

**의도적 미스컨피그(Azure, 5~6개):** Storage public access 허용 + 민감 파일, NSG 0.0.0.0 오픈, 과도 RBAC 역할, 미암호화, 공개 IP, App Registration 과도 권한.

---

## 15. 에이전틱 엔진 — 공유 코어 + 도메인 로직

| 에이전트 | 공통 역할 | 설정 도메인 | 워크로드 도메인 |
|---|---|---|---|
| Orchestrator | 파이프라인·핸드오프 | (공유) | (공유) |
| Triage | enrichment·우선순위 | 설정 finding | 취약점/권한 finding |
| Hypothesis | 가설 생성 | 컴플라이언스 위반 영향 | attack-path(권한+취약점+설정) |
| Evidence | read-only 검증 | 관련 설정 확인 | 이미지·워크로드·권한 확인 |
| Reasoning | 종합·신뢰점수·리포트 | 컴플라이언스 리포트 | 공격경로 리포트·우선순위 |

---

## 16. RAG 코퍼스

- **A. 기준·표준(필수):** CIS AWS/Azure/Kubernetes Benchmark, AWS FSBP, Well-Architected 보안. ※ CIS 재배포 금지 → private.
- **B. 조치(필수):** Security Hub 컨트롤 레퍼런스, AWS 서비스별 베스트프랙티스, Defender 권고, Prescriptive Guidance.
- **C. 위협·우선순위(강추):** MITRE ATT&CK(Cloud·Containers), CISA KEV, OWASP Top 10.
- **D. 한국 규제(차별화):** ISMS-P, CSAP, 개인정보보호법 요약.
- **E. 자체 작성(필수):** remediation 플레이북, 조치 카탈로그(allowlist+승인), 심각도 루브릭, 취약점 트리아지 루브릭(KEV+EPSS), 운영 런북.
- **F. 스키마(선택):** ASFF/OCSF, Prowler/Trivy/Checkov 룰 정의.
- **G. 워크로드/공급망:** 컨테이너 보안 가이드, Pod Security Standards, SLSA, Sigstore.

청킹: "컨트롤/룰 1개 = 1청크" + `{cloud, service, framework, control_id, severity, isms_p, remediable, lifecycle}`.
MVP 코퍼스: A(CIS AWS+K8s) + FSBP + C(KEV) + E(자체 루브릭).

---

## 17. 거버넌스 & AI 안전

- **Read-only first** — 에이전트 기본 조회만. 변경은 분리된 승인 경로로만.
- **최소권한** — 스캔 롤(read-only) ↔ 조치 롤(격상) 분리. IRSA/단기 STS. 시크릿은 Secrets Manager+KMS.
- **Explainable** — 모든 판정에 근거·신뢰점수·증거.
- **불변 감사로그** — S3 + Object Lock.
- **휴먼인더루프** — 비가역 조치는 승인 후. dry-run·롤백·allowlist.
- **OWASP Top 10 for LLM/Agentic** — 프롬프트 인젝션·도구 오용 방어 + Bedrock Guardrails.

---

## 18. Shift-Left & 공급망

1. **IaC 게이트** — PR 시 Checkov/OPA가 미스컨피그 검사 → 임계 위반 머지 차단. [핵심]
2. **이미지 게이트** — CI에서 Trivy 스캔 → KEV 등재 Critical 시 빌드 실패. [핵심]
3. **공급망 무결성** — Syft SBOM + cosign 서명, ArgoCD가 미서명 거부. [보너스]
4. **런타임 피드백** — 배포 워크로드를 Inspector로 점검, 신규 CVE를 CI로 피드백(폐루프). [핵심 일부]

---

## 19. 테스트 전략

핵심 원리: **의도적 결함을 심으면(정답지) → 스캐너가 잡고 → 관제 앱에 뜬다. 그 흐름 전체가 테스트.**

1. **미스컨피그 탐지** — IaC에 공개 버킷·열린 SG 심고 배포 → Config/Prowler/Security Hub가 잡는지. 심은 개수 = 기대 findings(정답지 명확).
2. **CVE 탐지** — 취약 베이스 이미지로 빌드 → Trivy/Inspector가 잡는지. KEV 등재분 넣어 우선순위 로직도 검증.
3. **역방향(수정→소멸)** — 버킷 private로 재배포 → finding 사라지는지. remediation·드리프트 검증.
4. **합성 finding 주입** — OCSF 가짜 finding을 파이프라인에 직접 주입 → 스캐너 안 기다리고 엔진·RAG·대시보드 빠른 반복.
5. **attack-path 골든 시나리오** — 공개버킷+과도권한+취약파드+Azure 민감데이터 동시 심기 → 하나의 탈취 경로로 묶는지(데모 하이라이트).

도구: CloudGoat/AWSGoat/Terragoat 패턴으로 취약 IaC 구성(정답지). golden findings 세트로 CI 회귀 테스트.

---

## 20. KPI

| 지표 | 목표 |
|---|---|
| MTTR_remediate(탐지~개선) | 수기 대비 대폭 단축 |
| 자동 설명률 | finding 중 AI가 근거와 함께 설명한 비율 |
| 우선순위 정확도 | attack-path 우선순위 vs 실제 위험 일치 |
| 멀티클라우드 커버리지 | AWS+Azure findings 통합·정규화 성공률 |
| Shift-Left 차단율 | CI에서 프로덕션 전 차단된 비율 |
| 취약점 우선순위 적중률 | KEV/EPSS 기반 vs 실제 악용 가능성 |
| 자동개선 안전성 | 자동 remediation 롤백/오류율 |
| 감사 완전성 | 모든 판정 근거·로그 100% |

---

## 21. 개발 로드맵 (2주 압축 · 2인 병렬)

### Week 1 — 뼈대 + 핵심 루프
| Day | 트랙1(설정·CI/CD) | 트랙2(워크로드·관측) |
|---|---|---|
| 1–2 | 계정·Terraform 골격, Config/Security Hub/Prowler 활성화, **SSO 검증** | EKS·ArgoCD·ECR 골격, 취약 타깃앱 배포 |
| 3–4 | 공유 수집 파이프라인·OCSF 정규화 | Inspector/Trivy 연동, 이미지 취약점 finding |
| 5 | **Bedrock finding 설명(RAG #1) 작동** | kube-bench(KSPM), CIEM 신호 |

### Week 2 — 깊이 + 멀티클라우드 + 마감
| Day | 트랙1 | 트랙2 |
|---|---|---|
| 6–7 | 우선순위 정렬(#2)·관제 대시보드 v1 | attack-path 그래프 1차, 관측 스택 |
| 8 | **Azure Defender + Entra 통합(멀티클라우드)** | 크로스클라우드 attack-path 시나리오 |
| 9 | Shift-Left CI 게이트 + 자동개선 1~2종(HITL) | 워크로드 finding 대시보드 연계 |
| 10 | 데모 완성 + KPI 측정 + 스크린샷/영상 | 〃 |

**우선순위 컷라인:** ① 절대사수 = CSPM 본체+RAG 설명+대시보드+Azure 통합+Shift-Left+KSPM ② 보너스 = 공급망 서명, attack-path 정교화, ISMS-P 리포트 ③ 확장 = CWPP 런타임, SOC.
**이후:** 개발 종료 → PPT·문서·발표.

---

## 22. 비용 · 무료 티어 가드레일

- 크레딧 소멸 트리거: **Organizations / Identity Center / Control Tower → 절대 안 켬.**
- Config·Security Hub·Inspector·Macie·Defender는 종량제 → **데모 기간만 켜고 `destroy`.**
- EKS: **NAT 제거(VPC 엔드포인트)**, **spot + 작은 노드**, 미사용 시 destroy, **Budgets 알림($50/$100)**.
- Azure: Storage 거의 무료, VM 생략 시 컴퓨팅 0, Defender 소액(데모만).
- 오픈소스(Trivy·Checkov·kube-bench·cosign)는 컴퓨팅 비용만.
- 인증 레이어(Cognito·IAM·Entra 무료)는 사실상 $0.

---

## 23. 확장 방향 (본체 아님)

- **CWPP 런타임** — OCSF 스키마·대시보드에 자리만 비워둠 → GuardDuty Runtime/Falco 입력 연결 시 반나절~하루.
- **탐지/SOC** — 같은 엔진에 위협 알림 입력 추가 시 인시던트 트리아지로 확장.
- **자율성 점진 확대** — 신뢰점수 높은 저위험부터 자동 개선 범위 확대.
- **GCP 추가** — Security Command Center로 3-클라우드.
- **Azure 자동개선** — Azure Policy 기반 remediation.

---

## 24. 미확정 (다음에 닫을 것)

- [ ] 프로젝트 정식 명칭 / 레포 네이밍
- [ ] 레포 분할(모노레포 vs 멀티레포, Terraform 모듈 경계, 공유 코어 위치)
- [ ] 타깃 앱 마이크로서비스 세부(개수·기능·미스컨피그·취약 이미지 — 완전한 목록)
- [x] **벡터DB = pgvector (RDS/Aurora PostgreSQL)** 확정 — 코퍼스 규모 작아 OpenSearch Serverless는 오버스펙·고비용. 저렴·단순·finding 메타데이터와 동거 가능.
- [ ] attack-path 구현(새 Security Hub exposure vs 커스텀 그래프 vs 병행)
- [ ] 자동 조치 카탈로그 1차 범위
- [ ] MVP 데모 시나리오 최종 확정

---

*v5 — 멀티클라우드(AWS 워크로드 / Azure 신원·데이터) 강점 분업, 앱·Bedrock·SSO·테스트 확정. 명칭·레포·세부는 다음 단계.*
