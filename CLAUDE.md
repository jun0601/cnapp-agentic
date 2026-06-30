# CLAUDE.md

> 이 파일은 Claude Code(및 협업자)가 이 레포에서 작업할 때 가장 먼저 읽는 기준 문서다.
> 상세 설계는 [docs/project-draft.md](docs/project-draft.md)(메인 설계서 v5), [docs/target-app-design.md](docs/target-app-design.md)(타깃 앱 상세), [docs/console-app-design.md](docs/console-app-design.md)(관제 앱 상세)에 있다. **이 셋이 단일 진실 공급원(SSOT)이며, 본 문서는 그 요약 + 협업 규칙이다.**

---

## 0. 작업 규칙 (모든 클로드·협업자가 지킬 것) ⚡

1. **시작 전:** 어떤 작업이든 시작 전 반드시 이 **CLAUDE.md를 먼저 읽고**, `git pull`로 최신 main을 받는다.
2. **변경 로그 기록:** 작업 중 중요한 변경·결정·방향 전환이 생기면 아래 [변경 로그](#변경-로그-최신이-위로)에 한 줄로 남긴다. *사소한 수정(오타·포맷 등)은 적지 않는다 — 다른 사람이 알아야 할 것만.*
3. **`[PULL 필요]` 태그:** 상대가 반드시 pull해야 할 중요 변경(설계 방향 전환, 핵심 결정, 구조 변경)은 변경 로그에 **`[PULL 필요]`** 태그를 붙여 명시한다.
4. **작업 후:** `commit` + `push`로 공유한다(커밋 메시지 `타입: 내용`). 상세 협업 규칙은 [6번](#6-협업-규칙-) 참조.

### 변경 로그 (최신이 위로)

> 형식: `날짜 / 작성자(준형·진우) / 한 줄 요약 / (필요 시 [PULL 필요])`. 최근 10~15개만 유지하고 오래된 항목은 [아카이브](#변경-로그-아카이브)로 내린다.

- **2026-06-30 / 진우 / 비용 최적화 + 설계 잔여 갭 해소** — Aurora→RDS PostgreSQL t3.micro 확정, NAT Instance+Gateway Endpoint 전략, Prowler Azure 파이프라인 진입 확정, 에이전트별 Bedrock 모델 배정(Haiku/Sonnet), CIEM 분담 독립 행, Entra CIEM RAG 룰북, D11·13번 갱신. project-draft v5.4·console-app-design·CLAUDE.md·target-app-design·infra-status.md 동기화. **`[PULL 필요]`**
- **2026-06-30 / 진우 / 공통 계약 4종 초안 확정 + 미확정 2건 닫음** — project-draft **4.4를 "합의 계약"으로 확장**해 ①OCSF-lite finding 스키마(식별자 `resource_id`로 일반화—Azure ARN 부재 대응, `dedup_key` 중복제거, `ai_status` AI레이어 분리) ②엔진 입출력(Evidence→Reasoning) ③attack-path 그래프 JSON ④Evidence 툴 allowlist(read-only) 초안을 박음. 코딩 시 `contracts/*.json`으로 졸업(별도 schema.md 안 만듦). **계약우선/목업우선 전략**(목업 finding 먼저 커밋→직렬 의존 끊기) 명시. 24번 미확정에서 **레포=모노레포 확정**, **attack-path 계산=커스텀 엔진 확정**. console 5·6.1을 4.4 참조 + `resource_id`로 동기화. ※핵심영역 분담·demo-real 범위는 여전히 진우 협의 대기. **`[PULL 필요]`**
- **2026-06-30 / 진우 / 작업 분담 표 통합 + 실명(준형/진우) 반영** — 앱·토대(확정)와 핵심 영역(협의중)을 한 표의 상태 열로 통합, 담당을 트랙1·트랙2 → 준형·진우로 교체. 분담은 상시 협의로 조정되는 살아있는 문서임을 명시. 두 파일 동기화.
- **2026-06-30 / 진우 / 작업 분담 균형안 도입** — 각 영역(스캐너·수집·엔진·RAG·attack-path)을 반반으로, 의존성 순서·합의 인터페이스 2개(OCSF 스키마·엔진 입출력)·시간 컷 우선순위(엔진 능동조사 사수) 명시. 설계서 4·21번 + CLAUDE.md 5번 동기화. *핵심 영역 분담은 진우 협의 후 최종 확정.* **`[PULL 필요]`**
- **2026-06-30 / 진우 / Azure 역할을 데이터→신원(Entra ID) 중심으로 전면 전환** — 데이터(회원 PII)는 AWS S3 전용·Macie도 AWS 전용, Azure 점검은 Entra CIEM + Defender secure score, 골든 시나리오를 크로스클라우드 신원 탈취 경로로 교체. 설계서 3종·README·CLAUDE.md 모두 동기화. **`[PULL 필요]`**

### 변경 로그 아카이브

> (아직 없음 — 변경 로그가 15개를 넘으면 오래된 항목을 여기로 이동.)

---

## 1. 한 줄 요약

멀티클라우드(**AWS = 워크로드의 주인 / Azure = 신원의 주인(Entra ID)**) 환경의 설정(Posture)부터 워크로드·IaC 코드까지 **code-to-cloud 보안 위험을 점검·통합·상관분석**하고, 그 위에 **에이전틱 AI(Bedrock 멀티에이전트 + RAG)**로 발견 항목을 설명·우선순위화·자동 개선하는 **CNAPP형 보안 플랫폼**. (데이터/회원 PII는 AWS S3 전용 — Azure에는 데이터를 두지 않는다.)

---

## 2. 핵심 키워드

- **Multi-Cloud** — AWS(워크로드의 주인) + Azure(신원의 주인, Entra ID). *각 클라우드 장점대로 — 컨테이너 워크로드는 AWS, Microsoft 생태계 신원은 Azure.* 흩어진 보안 상태를 OCSF로 정규화해 단일 뷰로 통합하고, **AWS 워크로드 침해가 Azure 신원(Entra) 장악으로 번지는 크로스클라우드 attack-path**까지 추적. (데이터는 AWS S3 전용, 중복 저장은 명분이 약해 Azure는 신원만.)
- **CNAPP** — CSPM·CIEM·취약점·KSPM·데이터(DSPM 맛)·attack-path 6기둥. CSPM을 넓히지 않고 **워크로드(코드 방향)로 깊게** 심화. SOC(실시간 위협탐지/대응)는 범위 밖(확장 훅만).
- **Agentic** — 챗봇이 아니라 에이전트가 능동적으로 일한다. **챗봇 탈출의 단일 기준 = LLM이 read-only API를 스스로 호출해 증거를 모으는가(tool use).** Orchestrator → Triage → Hypothesis → Evidence → Reasoning 루프(가설→증거→판정).

---

## 3. 핵심 설계 결정 (요약) ✅

상세·근거는 설계서 11번. 가장 자주 부딪히는 결정만 추림:

아래 표는 각 설계 결정과 그 요점을 정리한 것이다.

| 결정 | 요점 |
|---|---|
| **단일 계정 / 단일 리전(서울)** | Organizations·Identity Center·Control Tower **절대 안 켬**(무료 크레딧 소멸 트리거). CloudTrail/Config는 전 리전 수집. |
| **키 없는 인증** | CI/CD는 GitHub OIDC→IAM Role, 파드는 IRSA/Pod Identity. 장기 자격증명 미사용. |
| **EKS + ArgoCD GitOps** | 워크로드 운영·배포의 핵심 축. |
| **앱 2개** | ① 취약 타깃 앱(findings 소스) ② 관제 앱(HALO의 NOVA 대응, 얼굴). **둘은 직접 통신 안 함 — agentless.** |
| **취약점은 IaC에 심음** | 앱 코드 버그가 아니라 인프라/설정 결함. 기능 최소, 결함 다양성 최대. |
| **Bedrock + 수동 RAG** | SageMaker 미사용. 벡터DB = **pgvector(RDS/Aurora PostgreSQL)** 확정(코퍼스 작아 OpenSearch는 오버스펙). |
| **앱 SSO = Cognito 허브** | Entra ID(IdP) ─SAML→ Cognito ─OIDC→ ALB(authenticate-oidc). 워크포스 SSO 크레딧 회피. |
| **Azure = 신원(Entra ID) 중심** | 점검 핵심은 **Entra CIEM**(과도권한 앱 등록·위험한 consent·권한상승) + **Defender for Cloud**(리소스 secure score, 멀티클라우드 통합 뷰). Security Hub는 AWS 전용, Prowler로 멀티클라우드 병행. **Azure에 데이터는 두지 않음**(Defender 데이터 탐지 미사용). |
| **데이터는 AWS S3 전용 / Macie도 AWS 전용** | 회원 PII는 AWS S3에만 보관, 데이터 탐지(DSPM 맛)는 **Macie(AWS S3 전용)**. Azure는 데이터 저장소가 아니라 신원의 주인. |
| **골든 시나리오 = 크로스클라우드 신원 탈취** | product 취약 이미지 침투 → order 과도 IRSA + **평문 시크릿의 Azure 자격증명** → member 공개 S3로 AWS PII 탈취 → 탈취 자격증명으로 **Azure Entra ID 과도권한 앱/계정 장악**(디렉터리 전체 통제권). MVP는 분석·시각화 수준, 실제 횡단 동작은 보너스. |
| **Read-only first + HITL** | 에이전트는 기본 조회만. 변경(remediation)은 분리된 승인 경로(Step Functions) + 불변 감사로그(S3 Object Lock). |

**연결 구조(꼭 기억):** 타깃 앱은 AWS/Azure에 *배포*만 됨 → 스캐너가 계정을 **read-only로 스캔** → findings → EventBridge→SQS→Lambda → OCSF 정규화 → pgvector/엔진 → 관제 앱이 findings 저장소를 **읽어서** 표시. 타깃 앱↔관제 앱 직접 API 없음.

---

## 4. 폴더 구조 🏗️

```
cnapp-agentic/
├── CLAUDE.md                 # 이 문서 — 작업 기준 + 협업 규칙
├── README.md
├── docs/                     # ★ 설계 SSOT (변경 시 반드시 여기 먼저 반영)
│   ├── project-draft.md      #   메인 설계서 v5 (방향·범위·아키텍처·로드맵)
│   ├── target-app-design.md  #   타깃 앱 상세 (결함 목록·골든 attack-path)
│   └── console-app-design.md #   관제 앱 상세 (화면 구조·백엔드·RBAC·RAG 매핑)
├── apps/
│   ├── target/               # 취약 타깃 앱 (커머스 3 마이크로서비스: product/order/member). findings 소스
│   └── console/              # 관제 앱 (React, posture·findings·attack-path·AI 설명/조치)
├── engine/                   # 공유 에이전틱 엔진 코어 (Bedrock 멀티에이전트 + RAG + OCSF 정규화)
└── infra/                    # Terraform IaC
    ├── shared/               #   공유 골격 (계정·VPC·EKS·인증·수집 파이프라인·벡터DB)
    ├── target/               #   타깃 앱 인프라 (★ 의도적 결함을 IaC에 심는 곳)
    └── console/              #   관제 앱 인프라 (S3+CloudFront·ALB·Cognito·Step Functions)
```

> **레포 = 모노레포 확정**(설계서 24번). 레포는 하나여도 배포는 폴더별 분리(target=EKS, console=S3+Lambda), Terraform state는 `infra/{shared,target,console}`별 분리. 코딩 시작 시 공통 계약은 `contracts/*.json`(project-draft 4.4 초안 졸업)으로 추가. 구조를 바꿀 땐 docs에 먼저 반영.

---

## 5. 작업 분담 (균형안 — 효율용 트랙)

> **원칙:** 일을 나누되 **둘 다 상대 영역까지 완전히 이해**한다. 각 영역을 반반 갈라 양쪽이 핵심을 다 만진다. 상세·의존성·인터페이스는 설계서 4번이 SSOT.
> ⚠️ **이 분담은 상시 협의로 계속 조정되는 살아있는 문서.** 변경 시 이 표와 설계서 4번을 **함께** 갱신한다.

| 영역 | 준형 | 진우 | 상태 |
|---|---|---|---|
| 앱 | 타깃 앱(결함 심기) | 관제 앱(대시보드·시각화) | 확정 |
| 토대 | CI/CD·Shift-Left·**공유인프라 주도** | 모니터링·관제·추적(Grafana·CloudTrail) | 확정 |
| 스캐너-CSPM | CSPM(Config·Prowler·Security Hub·**Macie(AWS S3)**) | 워크로드(Inspector·Trivy·kube-bench·**Defender(Azure)**) | 협의중 |
| 스캐너-CIEM | IAM Access Analyzer(AWS) | Entra ID(Azure — **Prowler entra_id_\* 체크**) | 협의중 |
| 수집·정규화 | 수집부(EventBridge→SQS) | 정규화부(Lambda→OCSF) | 협의중 |
| 엔진(Bedrock) | **Evidence(tool use)**·Triage | Hypothesis·**Reasoning**·Orchestrator | 협의중 |
| RAG | 코퍼스·임베딩·pgvector 적재 | 검색·LLM 답변 생성 | 협의중 |
| attack-path | 그래프 데이터 모델 | 상관 로직·내러티브 | 협의중 |

> 앱·토대=확정, 핵심 영역(스캐너·수집·엔진·RAG·attack-path)=**협의중**(둘이 상시 조율).

- **의존성(병목):** 0 공유인프라(준형 최우선) → 1 앱·모니터링 ∥ → 2 스캐너 ∥ → 3 수집→정규화 → 4 RAG ∥ → 5 엔진(Evidence∥Reasoning) → 6 출력 ∥ → 7 데모 합류.
- **공통 계약 4종 초안 확정(project-draft 4.4):** ① OCSF-lite 스키마(`resource_id`·`dedup_key`·`ai_status`) ② 엔진 입출력(Evidence→Reasoning) ③ attack-path 그래프 JSON ④ Evidence 툴 allowlist(read-only). `contracts/mock-findings.json` 먼저 커밋 → 직렬 의존 끊고 병렬 작업 가능.
- **시간 컷 우선순위:** 엔진 능동조사(1) > attack-path 상관(2) > 스캐너·수집·RAG(3) > 관제앱·CI/CD·포장(4). **"AI가 스스로 증거 모아 공격경로 판단하는 한 장면"** 사수.

**공유 자산(양쪽 함께):** 수집 파이프라인(EventBridge→SQS→Lambda, OCSF 정규화), 에이전틱 엔진 코어(`engine/`), 인프라 골격(`infra/shared/`), 관제 대시보드(`apps/console/`).

---

## 6. 협업 규칙 🔒

1. **작업 시작 전 `git pull`** — 항상 최신 main을 받고 시작. 충돌 줄이기.
2. **작업 후 `commit` + `push`** — 의미 단위로 커밋하고 바로 push해 상대가 받을 수 있게. 커밋 메시지는 `타입: 내용`(예: `feat: ...`, `docs: ...`, `infra: ...`).
3. **설계 변경은 docs에 먼저 반영** — 방향·범위·구조·결정이 바뀌면 [docs/](docs/)의 해당 설계 문서(project-draft / target-app-design / console-app-design)를 **먼저** 업데이트하고, 영향이 있으면 본 CLAUDE.md도 갱신. 코드/문서 불일치를 남기지 않는다.
4. **무료 티어 가드레일 준수** — Organizations/Identity Center/Control Tower 금지. 종량제 서비스(Config·Security Hub·Inspector·Macie·Defender)는 데모 기간만 켜고 `destroy`. Budgets 알림 유지.
5. **보안 기본** — 장기 키 커밋 금지(OIDC/IRSA 사용), 시크릿은 Secrets Manager+KMS. 에이전트는 read-only first, 변경은 HITL 승인 경로로만.

---

## 7. 앞으로의 작업 기준 🗓️

- **모든 작업은 `docs/`와 이 `CLAUDE.md`를 기준으로 진행한다.** 새 기능·결정·구조 변경은 먼저 설계 문서와 정합성을 확인하고, 어긋나면 문서를 갱신한 뒤 코드를 작성한다.
- 우선순위 컷라인(설계서 21번): **① 절대사수** = CSPM 본체 + RAG 설명 + 대시보드 + Azure 통합 + Shift-Left + KSPM, **② 보너스** = 공급망 서명·attack-path 정교화·ISMS-P 리포트, **③ 확장** = CWPP 런타임·SOC.
- 미확정 항목(설계서 24번)은 결정될 때마다 docs에 반영하고 여기 요약을 갱신한다.
