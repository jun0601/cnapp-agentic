# 에이전틱 AI 기반 멀티클라우드 CNAPP 보안 플랫폼

> 멀티클라우드(**AWS = 워크로드의 주인 / Azure = 신원의 주인(Entra ID)**) 환경의 설정부터 워크로드·IaC 코드까지 **code-to-cloud 보안 위험을 점검·통합·상관분석**하고, 그 위에 **에이전틱 AI(Bedrock 멀티에이전트 + RAG)**로 발견 항목을 설명·우선순위화·자동 개선하는 CNAPP형 보안 플랫폼.
>
> 클라우드 보안 엔지니어 포트폴리오 목적의 **2인 협업 개인 프로젝트**입니다. 현재 단계: 설계 문서·공통 계약 정합 완료 · **구현 진행 중** — 공통 계약(INTERNAL control 14종·골든 목업·CI 게이트) + 공유 인프라 스캐폴드 + TF state 부트스트랩 + **관제 앱(`apps/console`) 8화면 목업 동작** + **타깃 앱(`apps/target`) shop 포털·member 서비스 실행** + 결함 IaC(`infra/target`) + **엔진 5단계 능동조사·attack-path 상관·정규화부·RAG·Trivy 스캐너(목업 동작)** + **❤️ 엔진 실 tool-use(Phase1) 실검증 완료**(실 Bedrock Claude Haiku가 실 S3를 스스로 read-only 조사 → CONFIRMED, 2026-07-02) + **🔗 Phase2 end-to-end 배선 관통**(스캐너→정규화→상관→엔진→RAG `run_e2e.py`) + **관제 백엔드(`apps/console-backend`)·배포 인프라 5층(`infra/`)·pgvector 스키마·Lambda 핸들러** 코드 완성(전 terraform `validate` 통과). **다음 = 단계별 실 apply**(apply→검증→destroy).

### 📂 이 레포는 무엇인가 / docs 안내

설계의 단일 진실 공급원(SSOT)은 `docs/` 폴더이며, 각 문서의 역할은 다음과 같다.

| 문서 | 무엇인지 |
|---|---|
| [docs/project-draft.md](docs/project-draft.md) | **전체 설계서(SSOT)** — 방향·범위·핵심 결정(D1~D19)·아키텍처·로드맵·미확정 항목 총괄. 여기부터 읽는다. |
| [docs/target-app-design.md](docs/target-app-design.md) | **타깃 앱 설계도** — 일부러 취약하게 만드는 고객사 워크로드(findings 소스). 기능 베이스(retail-store)·의도적 결함 목록·골든 attack-path + **§7 구현 청사진**(결함↔IaC 토글 매핑). |
| [docs/console-app-design.md](docs/console-app-design.md) | **관제 앱 설계도** — 우리가 만드는 보안 관제 플랫폼(NOVA 대응). 화면·백엔드·RBAC·RAG↔UI 매핑 + **§15 구현 청사진**(스택·API 표면·화면↔mock). |
| [docs/manual-infra.md](docs/manual-infra.md) | **수동 관리 리소스 현황** — 콘솔/CLI로 직접 설정한 리소스(계정 초기화·Terraform 부트스트랩·Azure SSO 등). Terraform 관리 대상 제외. |
| [docs/cost-strategy.md](docs/cost-strategy.md) | 💰 **비용 최적화 전략** — 무료 크레딧·평가판 안에서 프로덕션급 아키텍처를 증명한 FinOps 결정 원장(mock-first·경량 대체·모델 티어링·destroy 규율 + 정직한 트레이드오프). |
| [CLAUDE.md](CLAUDE.md) | **작업 기준·협업 규칙** — 위 설계서들의 요약 + 협업 규칙. |

---

## 🔑 핵심 키워드

- **Multi-Cloud** — AWS(워크로드의 주인)와 Azure(신원의 주인, Entra ID)의 흩어진 보안 상태를 OCSF로 정규화해 단일 뷰로 통합하고, **AWS 워크로드 침해가 Azure 신원 장악으로 번지는** 클라우드 경계를 넘는 위험 경로를 추적한다. *각 클라우드의 장점대로 — 컨테이너·클라우드 네이티브 워크로드는 AWS, Microsoft 생태계 신원은 Azure.* (데이터 중복 저장은 명분이 약해, 데이터는 AWS S3에만 둔다.)
- **CNAPP** — CSPM·CIEM·취약점·KSPM·데이터 보안·attack-path를 하나의 그래프로 묶어, 단일 도구로는 못 잡는 **독성 조합(toxic combination)**을 탐지한다.
- **Agentic AI** — 질문해야 답하는 챗봇이 아니라, 에이전트가 read-only API를 스스로 호출(tool use)해 증거를 모으고 가설→증거→판정 루프로 위험을 추론한다.

---

## ✨ 주요 기능

- **6기둥 CNAPP 점검** — CSPM(설정), CIEM(권한), 취약점, KSPM(쿠버네티스), 데이터 보안(DSPM 맛), attack-path를 통합 점검.
- **에이전틱 AI 분석** — finding 자동 설명(근거·조치법 카드), 위험 우선순위 자동 정렬, attack-path 내러티브 생성, 그리고 read-only tool use로 증거를 능동 수집.
- **크로스클라우드 attack-path** — "AWS 취약 워크로드 침투 → 과도 권한 측면 이동 + **평문 시크릿에서 Azure 자격증명 발견** → 공개 S3의 PII 탈취 → **탈취 자격증명으로 Azure Entra ID 신원 장악(과도권한 앱/계정)**"처럼, 개별적으로는 중간 위험인 finding들을 하나의 신원 탈취 경로로 엮어낸다. *(MVP는 이 경로를 분석·시각화하는 수준, 실제 AWS→Azure 횡단 동작 구현은 보너스.)*
- **Shift-Left CI 게이트** — PR 단계에서 Checkov/OPA(IaC 미스컨피그)와 Trivy(이미지 CVE)로 검사해, 위험한 변경이 프로덕션에 가기 전에 차단한다.
- **휴먼인더루프 자동 개선** — 에이전트는 기본적으로 조회만 수행하고, 변경(remediation)은 승인 경로를 통해서만 적용하며 모든 판정·조치를 불변 감사로그로 남긴다.

---

## 🏗️ 아키텍처 개요

```
[ 입력: CNAPP 신호 ]
  AWS 설정/워크로드 :  Config · Security Hub · Prowler · Inspector · Trivy · kube-bench · IAM Access Analyzer · Macie(S3 전용)
  AWS 빌드 게이트   :  CI에서 Checkov/OPA(IaC) · Trivy(이미지)
  Azure            :  Entra ID(CIEM: 과도권한 앱·위험한 consent·권한상승) · Defender for Cloud(리소스 secure score)
        │  (ASFF / OCSF 정규화)
        ▼
  EventBridge → SQS → Lambda
        │
  ┌──── 공유 에이전틱 엔진 (Bedrock 멀티에이전트 + RAG) ────┐
  │  Orchestrator → Triage → Hypothesis → Evidence → Reasoning │
  │  거버넌스: 최소권한 · read-only first · 불변 감사로그       │
  └────────────────────────────────────────────────────────────┘
        │
  [ attack-path 그래프 ]  권한 + 취약점 + 설정 + 데이터 → 탈취 경로(AWS 워크로드→Azure 신원 크로스클라우드)
        │
  위험 → 자동 개선 제안 → 휴먼인더루프(승인) → Step Functions → 감사로그
        │
  [ 관제 앱 ]  posture 점수 + findings + attack-path + AI 설명/조치  (React · S3+CloudFront)
```

**연결 구조 (agentless):** 점검 대상인 타깃 앱은 클라우드 계정에 *배포*만 되고, 스캐너가 계정을 외부에서 **read-only로 스캔**한다. findings는 수집 파이프라인을 거쳐 정규화·저장되며, 관제 앱은 그 저장소를 읽어 표시한다. 타깃 앱과 관제 앱 사이의 직접 통신은 없다.

---

## 🧰 기술 스택

영역별로 사용하는 주요 기술은 다음과 같다.

| 영역 | 사용 기술 |
|---|---|
| **AWS 보안** | CloudTrail, Config, Security Hub, Prowler, Inspector, IAM Access Analyzer, Macie(S3 민감데이터 전용) |
| **Azure 보안** | Microsoft Entra ID(신원·CIEM 핵심), Defender for Cloud(리소스 secure score) — *데이터 저장소 아님* |
| **워크로드 / 배포** | EKS, ECR, **ArgoCD(GitOps CD)**, **Karpenter(노드 오토스케일·spot·consolidation) · HPA(파드)**, IRSA |
| **CI/CD** | **GitHub Actions**(CI: 회귀 + Shift-Left 스캔 Trivy·Checkov, $0) → **ArgoCD**(CD: GitOps pull-sync). 선언형 코드 = [`gitops/`](gitops/) |
| **Shift-Left** | GitHub Actions(OIDC), Checkov / OPA, Trivy, kube-bench |
| **에이전틱 AI** | Amazon Bedrock(멀티에이전트), 수동 RAG, pgvector(RDS PostgreSQL t3.micro) |
| **수집 / 오케스트레이션** | EventBridge, SQS, Lambda, Step Functions, OCSF 정규화 |
| **인증** | Microsoft Entra ID(IdP, SAML) → Cognito(허브) → ALB(authenticate-cognito) |
| **관제 앱 (프론트)** | Vite + React + TypeScript, TanStack Query, Tailwind, React Flow(attack-path 그래프), Recharts(점수), MSW(mock 하네스) |
| **관제 앱 (백엔드)** | TypeScript Lambda (findings 읽기 API) — *폴리글랏: console=TS / engine·pipeline=Python* |
| **관측 / 호스팅** | S3 + CloudFront, kube-prometheus-stack |
| **IaC** | Terraform |

---

## 🏗️ 폴더 구조

> 마커: ✅ 내용 있음(구현/스캐폴드) · 📁 빈 폴더(자리 확보) · ⬜ 아직 미생성(계획).
> **각 영역 하위폴더 = 소유자별 2개**(준형/진우, 공유는 예외 — §4.6). ⬜ 영역의 하위폴더 이름은 **가제(계획)** — 실제 폴더는 그 단계에서 생성.

```
cnapp-agentic/
├── CLAUDE.md                 ✅ 작업 기준 · 협업 규칙 · 변경 로그(읽기 우선)
├── README.md                 ✅
├── troubleshooting.md        ✅ 작업 로그 (트러블슈팅 + 진행, [영역] 태그)
├── cnapp-architecture.svg    ✅ 아키텍처 다이어그램
├── run_e2e.py                ✅ Phase2 end-to-end 러너(스캐너→정규화→상관→엔진→RAG 한 줄 관통)
├── .github/workflows/        ✅ CI — ci.yml(10개 데모·run_e2e·validate 회귀 + Trivy/Checkov Shift-Left)
├── gitops/                   ✅ CD(ArgoCD Application) + 오토스케일링(Karpenter·HPA) 선언형 — apply는 EKS 세션
├── contracts/                ✅ ★공유 이음새 계약(7종 JSON Schema) + control-catalog(14종) + 골든 mock 3종 + validate.py
├── docs/                     ✅ 설계 SSOT — project-draft · target/console-app-design · manual-infra · cost-strategy
├── apps/
│   ├── target/               ✅ 취약 타깃 앱 (product · order · member[Python] + PII seeder) — 코드만
│   ├── console/              ✅ 관제 앱 프론트 (Vite+React+TS, 8화면 MSW 목업 동작) — 코드만
│   └── console-backend/      ✅ 관제 앱 백엔드 (ALB→Lambda, findings 읽기 API, mock+실 pgvector 스텁) — 코드만
├── engine/                   ✅ 공유 에이전틱 엔진 (전체 루프 동작) — 하위=소유자별
│   ├── core/                 (공유) contracts · tools · case
│   ├── evidence/             (준형) triage · evidence — 능동조사
│   └── reasoning/            (진우) hypothesis · reasoning · orchestrator
├── scanners/                 🔨 스캐너 연동 (목업 동작)
│   ├── cspm/                 ✅ SecurityHub·Macie·Prowler → 계약⑤ 봉투(mock+실 boto3/CLI) (준형)
│   ├── workload/             ✅ Trivy ✅ · Inspector·kube-bench·Defender ⬜ (진우)
│   └── ciem/                 ✅ Prowler entra_id_* → 계약⑤ 봉투(mock+실 CLI 위임) (진우)
├── pipeline/                 ✅ 수집·정규화 (목업 동작)
│   ├── ingest/               ✅ EventBridge/S3 이벤트 → 계약⑤ 봉투 → SQS (준형)
│   └── normalize/            ✅ Lambda→OCSF (ASFF·prowler·trivy→OCSF-lite, dedup·역인덱스) (진우)
├── rag/                      ✅ RAG (목업 동작)
│   ├── corpus/               ✅ 청크 → Titan 임베딩 → pgvector 적재(계약⑥, mock+실) (준형)
│   └── retrieval/            ✅ 검색 · LLM 답변 (진우)
├── attackpath/               ✅ finding→그래프 상관 동작 (골든 정합 OK)
│   ├── model/                (준형) 그래프 데이터 모델·불변식 검증 ✅
│   └── correlation/          (진우) R1~R5 상관·2-pass backfill ✅
└── infra/                    Terraform (레이어드) — shared 먼저 → 영역별. 전 레이어 validate 통과
    ├── shared/               ✅ VPC·NAT·EKS·ECR·RDS pgvector·OIDC·IAM + db/schema.sql(pgvector 6테이블)
    ├── target/               ✅ 취약 워크로드 + 의도적 결함 IaC(f3·f4·f6 var.enable_* 토글)
    ├── console/              ✅ S3+CloudFront·ALB(authenticate-cognito)→Lambda·Cognito SSO·조치 SFn
    ├── pipeline/             ✅ EventBridge→SQS→ingest/normalize Lambda
    ├── engine/               ✅ 상관·오케스트레이터 Lambda·Bedrock IAM·조치 Step Functions(HITL)
    ├── slice/                ✅ 엔진 실 tool-use 최소비용 검증 픽스처(Phase1 — 레이어 아님)
    └── {scanners,rag,attackpath} ⬜ 영역별 terraform(미구현 — 데모 핵심 경로 밖)

# 컴포넌트 폴더(scanners·pipeline·engine·rag·attackpath)는 코드만 — 배포는 CI가 infra/에서 apply.
# 폴더는 사람이 아니라 컴포넌트로 나눔(소유·이음새는 docs/project-draft 4.6).
```

---

## 👥 역할 분담 (2인)

> 원칙 — 일을 나누되 **둘 다 상대 영역까지 이해**한다. 각 영역을 반반 갈라 양쪽이 핵심을 다 만진다. 상시 협의로 조정되는 살아있는 분담이며, 상세 SSOT는 [CLAUDE.md §5](CLAUDE.md) · [project-draft §4.1](docs/project-draft.md).
> **영역 순서 = 대략의 진행 순서**(앱·환경 → 인프라 → 스캐너 → 수집·정규화 → RAG → 엔진 → attack-path). 정확한 순서는 아니고 "이 느낌으로 쌓아간다".
>
> **⚠️ 상태는 2축 — 각 칸은 `⬜ 없음 → 🔨 목업/스캐폴드 → ✅ 완성`을 두 번(목업 축·실 축) 거친다:**
> - **진행(목업)** = 인프라·AI 0원, 로직만(`contracts/mock-*.json` 기반). `⬜`/`🔨`/`✅`.
> - **실(real) 전환** = 진짜 클라우드·Bedrock 동작. `⬜ 미착수` / `🔨 코드·검증전` / `✅ 실동작`.
> - 👉 **표의 '진행(목업)' ✅는 로직만 완성**이라는 뜻이고, 진짜 동작 여부는 마지막 **'실(real) 전환'** 컬럼이다. **첫 실동작 칸 = 엔진(Phase1) ✅**(2026-07-02 실 Bedrock + 실 S3 검증) — 나머지 칸은 Phase2~에서 실 전환.

| 영역 | 준형 | 준형 진행(목업) | 진우 | 진우 진행(목업) | 🚀 실(real) 전환 |
|---|---|---|---|---|---|
| 🖥️ **앱 & 환경 세팅** | 타깃 앱 · 관제 앱 **2개 개발** | ✅ 목업 동작(콘솔 8화면 · 타깃 member+포털) | **AWS/Azure 환경**(M365·Entra 데모 테넌트·계정 초기) | 🔄 AWS 계정 ✅ / Azure 테넌트 진행중 | ⬜ apply 시 배포(Phase2~) · Azure 테넌트·AWS 계정은 실물 ✅ |
| 🏗️ **공유 인프라 · 토대** | `infra/` 5층(shared·target·console·pipeline·engine) · CI/CD · Shift-Left | 🔨 코드 완성·`validate` 통과(apply 전) | 모니터링·운영관제(Grafana·CloudTrail) | ⬜ 예정 | ⬜ apply 전(TF state 버킷만 실물 ✅) |
| 🔍 **스캐너** | CSPM(Config·Prowler·Security Hub·Macie) · IAM Access Analyzer | ✅ 목업 동작(`scanners/cspm`, 골든 5종) | 워크로드(Inspector·Trivy·kube-bench·Defender) · Entra CIEM(`scanners/ciem`) | 🔨 Trivy ✅ · Entra CIEM ✅(f8·f9·f16·f17 골든) · Inspector·kube-bench ⬜ | ⬜ Phase2 첫 실스캐너(scan_securityhub/scan_prowler 실계정) → Phase3 확장 |
| 📥 **수집 · 정규화** | 수집부 (EventBridge→SQS) | ✅ 목업 동작(`pipeline/ingest`) | 정규화부 (Lambda→OCSF) | ✅ 목업 동작(`pipeline/normalize`) | ⬜ Phase2(Lambda 배포 + 실 finding) |
| 📚 **RAG** | 코퍼스 · 임베딩 · pgvector 적재 | ✅ 목업 동작(`rag/corpus`, 계약⑥ 24청크) | 검색 · LLM 답변 생성 | ✅ 목업 동작(`rag/retrieval`) | ⬜ Phase3(pgvector 적재 + Bedrock 임베딩) |
| 🧠 **엔진 (Bedrock)** | Evidence(tool use) · Triage | ✅ 목업 능동조사(`engine/`) | Hypothesis · Reasoning · Orchestrator | ✅ 목업 동작(전체 루프) | **✅ Phase1 완료(2026-07-02)** — 실 Bedrock(Haiku)이 실 S3를 read-only **자가 조사 → CONFIRMED**(apply→`run_real`→destroy) |
| 🕸️ **attack-path** | 그래프 데이터 모델 | ✅ 모델·불변식 검증(`attackpath/model`) | 상관 로직(R1~R5) · 내러티브 | ✅ R1~R5 상관·2-pass backfill | ⬜ Phase2에 엮임(실 finding 상관) |

> ⚠️ "관제"는 두 가지 — **관제 "앱"**(CNAPP 보안 대시보드 제품) = 준형 / **운영 "관제"**(Grafana·CloudTrail 플랫폼 관측) = 진우. 애플리케이션 2개는 모두 준형이 개발한다.
>
> **진행 순서(내가 뚫는 순서) = 표 위→아래가 아니라 위험 순:** **Phase1** 엔진 행을 목업→실(엔진 실 tool-use, ← 지금) · **Phase2** 세로 한 줄을 실로 연결(스캐너 1개→수집·정규화→엔진→attack-path→콘솔) · **Phase3** 나머지 칸 폭 채우기(스캐너 다수·RAG·CI/CD·ISMS-P).

---

## 🚧 구현 현황 (Status)

| 영역 | 상태 |
|---|---|
| 📜 **공통 계약 (`contracts/`)** | ✅ **졸업** — 계약 7종 JSON Schema + INTERNAL control 카탈로그(14종) + 골든 시나리오 mock(findings·attack-path·case). `validate.py` 4-assert + GitHub Actions CI 게이트로 정합 보장 |
| 🖥️ **관제 콘솔 (`apps/console`)** | ✅ **8화면 목업 동작** — Vite+React+TS+Tailwind+TanStack+React Flow+MSW. 대시보드·Findings·Finding상세(Evidence 탭)·Attack-path + 조치·컴플라이언스·감사로그·로그인. MSW가 `contracts/mock-*.json` 서빙 → 백엔드·AWS 0으로 동작. `tsc`·`vite build` 통과 |
| 🛒 **타깃 앱 (`apps/target`)** | ✅ **member 실행 + shop 포털** — member(Python/FastAPI) 회원 REST + **PII seeder**(faker→S3, Macie 미끼) + 포털. product/order는 결함 매니페스트(f1·f2·f5). 모든 PII/시크릿 가짜 |
| 🖥️ **관제 백엔드 (`apps/console-backend`)** | ✅ **mock-first 동작** — ALB→Lambda(TS)로 프론트 API 표면(§15.2) 서빙 = MSW의 서버판. tsc 통과 + 스모크(findings·detail·attack-path·scores·**RBAC viewer403/approver200**·404) OK. `USE_MOCK=false`+`PG_DSN`로 pgvector 스왑. 콘솔 MSW→실 API 전환 준비 완료 |
| 🧩 **로직 계층 (전부 목업 동작 · exit 0)** | ✅ 엔진 5단계 능동조사(`engine`)·attack-path R1~R5 상관+그래프(`attackpath`)·수집부(`pipeline/ingest`)·정규화부(`pipeline/normalize`)·RAG 검색·답변(`rag/retrieval`)+코퍼스 적재(`rag/corpus`)·Trivy(`scanners/workload`)+CSPM(`scanners/cspm`) 스캐너. 각 영역 준형/진우 half 다 채워짐(계약 SSOT로 정합) |
| ❤️ **엔진 실 tool-use (Phase1 — 심장)** | ✅ **실검증 완료(2026-07-02)** — `infra/slice` apply → `run_real` → destroy 전 과정 실행. **실 Bedrock Claude Haiku가 스스로 `s3:GetBucketPolicy`·`GetPublicAccessBlock` 호출 → 실 S3 응답으로 판정 CONFIRMED(100%)** → 즉시 destroy(비용 ~$0). 챗봇 탈출(LLM 능동 tool use)이 목업이 아니라 **실제로 동작함을 증명** |
| 🔗 **Phase2 end-to-end 배선 (`run_e2e.py`)** | ✅ **관통 확인(2026-07-02)** — 스캐너(Trivy) → 정규화 → 상관(attack-path) → 엔진 → RAG를 **한 러너로 연결**, 스캐너발 CVE가 파이프라인 끝(엔진 판정·RAG 설명)까지 도달(exit 0). 정규화·상관은 실 코드 관통, 스캐너는 실 trivy 출력 동일 구조 JSON(⬜ 라이브 `trivy image`는 trivy 설치/CI 대기), 엔진·RAG는 무비용 Mock(실 tool-use는 Phase1) |
| 🏗️ **공유 인프라 (`infra/shared`·`infra/target`)** | ✅ **스캐폴드** — VPC·NAT Instance·EKS(spot·IRSA)·ECR·RDS pgvector·OIDC·Evidence/Bedrock IAM + 결함 IaC 토글(f3·f4·f6). `terraform validate`/`fmt` 통과. apply는 게이트 후 |
| 🚚 **배포 인프라 (`infra/console`·`pipeline`·`engine`)** | ✅ **코드 완성** — console(ALB authenticate-cognito→Lambda·Cognito SAML SSO·S3+CloudFront)·pipeline(EventBridge→SQS→정규화 Lambda)·engine(상관·오케스트레이터 Lambda + evidence/bedrock 정책 + **remediation Step Functions·실행기(`engine/remediation.py`)·감사 S3 Object Lock**). `fmt`+`validate` 3개 통과. Lambda=배포 가능 스텁+실코드 스왑 포인트. apply 전 TODO: ACM 인증서·Entra SAML 메타데이터·SM ARN. **slice=레이어 아닌 저비용 픽스처(문서 명시)** |
| 🗄️ **DB 스키마 + Lambda wrapper** | ✅ **코드 완성** — `infra/shared/db/schema.sql`(pgvector 6테이블: findings·attack_paths·cases·finding_explanations·remediation_requests·rag_chunks, 계약①③⑦⑥ 도출·멱등) + 핸들러 wrapper 4종(ingest·normalize·correlation·orchestrator, 기존 로직 재사용 + RDS I/O + 2-pass 발행, engine은 `REAL_TOOLS=1`이면 실 Bedrock tool-use). py_compile+import OK. ⬜ 실 RDS 대상 SQL은 apply 세션에서 라이브 검증 |
| 📦 **TF state 부트스트랩** | ✅ `cnapp-agentic-tfstate` 버킷(manual-infra §2) · **Bedrock 모델 액세스 ✅**(manual-infra §4) |
| ⚙️ **CI/CD (`.github/workflows/ci.yml`·`gitops/`)** | ✅ **코드 세팅** — CI(GitHub Actions: 10개 데모·run_e2e·validate 회귀 + Trivy/Checkov Shift-Left, $0) · CD(ArgoCD Application) + 오토스케일링(Karpenter spot·consolidation / HPA) 선언형. ⬜ CD/오토스케일 **실적용은 EKS apply 세션**(비용 규율). 근거 = cost-strategy §2.7 |
| ⏭️ **다음 = 단계별 실 apply** | ⬜ **예정** — 코드(앱·엔진·인프라 5층·스키마·wrapper)는 준비 완료. `apply→검증→destroy` 사이클로 실전환(EKS 첫 apply 직전 확인). SSO 라이브는 도메인+ACM 확보 후 |

> **전략 = 계약·목업 우선.** 실제 스캐너/엔진을 기다리지 않고 `contracts/mock-*.json`으로 관제 콘솔·엔진을 끝까지 만든 뒤 실데이터로 교체 — 직렬 의존을 두 병렬 트랙으로 분리한다.

---

## 📖 상세 설계

설계의 배경·결정 근거·로드맵 등 상세 내용은 상단 [📂 docs 안내](#-이-레포는-무엇인가--docs-안내) 표의 문서를 참고한다. (project-draft → target-app-design → console-app-design 순)

> 📌 상세 변경 이력은 [CLAUDE.md 변경 로그](CLAUDE.md#변경-로그-최신이-위로)와 [troubleshooting.md](troubleshooting.md)에서 관리한다(README는 현재 상태만 유지).
