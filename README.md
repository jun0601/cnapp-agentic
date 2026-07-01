# 에이전틱 AI 기반 멀티클라우드 CNAPP 보안 플랫폼

> 멀티클라우드(**AWS = 워크로드의 주인 / Azure = 신원의 주인(Entra ID)**) 환경의 설정부터 워크로드·IaC 코드까지 **code-to-cloud 보안 위험을 점검·통합·상관분석**하고, 그 위에 **에이전틱 AI(Bedrock 멀티에이전트 + RAG)**로 발견 항목을 설명·우선순위화·자동 개선하는 CNAPP형 보안 플랫폼.
>
> 클라우드 보안 엔지니어 포트폴리오 목적의 **2인 협업 개인 프로젝트**입니다. 현재 단계: 설계 문서·공통 계약 정합 완료 · **구현 진행 중** — 공통 계약(INTERNAL control 14종·골든 목업·CI 게이트) + 공유 인프라 스캐폴드 + TF state 부트스트랩 + **관제 앱(`apps/console`) 8화면 목업 동작** + **타깃 앱(`apps/target`) shop 포털·member 서비스 실행** + 결함 IaC(`infra/target`).

### 📂 이 레포는 무엇인가 / docs 안내

설계의 단일 진실 공급원(SSOT)은 `docs/` 폴더이며, 각 문서의 역할은 다음과 같다.

| 문서 | 무엇인지 |
|---|---|
| [docs/project-draft.md](docs/project-draft.md) | **전체 설계서(SSOT)** — 방향·범위·핵심 결정(D1~D19)·아키텍처·로드맵·미확정 항목 총괄. 여기부터 읽는다. |
| [docs/target-app-design.md](docs/target-app-design.md) | **타깃 앱 설계도** — 일부러 취약하게 만드는 고객사 워크로드(findings 소스). 기능 베이스(retail-store)·의도적 결함 목록·골든 attack-path + **§7 구현 청사진**(결함↔IaC 토글 매핑). |
| [docs/console-app-design.md](docs/console-app-design.md) | **관제 앱 설계도** — 우리가 만드는 보안 관제 플랫폼(NOVA 대응). 화면·백엔드·RBAC·RAG↔UI 매핑 + **§15 구현 청사진**(스택·API 표면·화면↔mock). |
| [docs/manual-infra.md](docs/manual-infra.md) | **수동 관리 리소스 현황** — 콘솔/CLI로 직접 설정한 리소스(계정 초기화·Terraform 부트스트랩·Azure SSO 등). Terraform 관리 대상 제외. |
| [CLAUDE.md](CLAUDE.md) | **작업 기준·협업 규칙** — 위 설계서들의 요약 + 협업 규칙. |

---

## 핵심 키워드

- **Multi-Cloud** — AWS(워크로드의 주인)와 Azure(신원의 주인, Entra ID)의 흩어진 보안 상태를 OCSF로 정규화해 단일 뷰로 통합하고, **AWS 워크로드 침해가 Azure 신원 장악으로 번지는** 클라우드 경계를 넘는 위험 경로를 추적한다. *각 클라우드의 장점대로 — 컨테이너·클라우드 네이티브 워크로드는 AWS, Microsoft 생태계 신원은 Azure.* (데이터 중복 저장은 명분이 약해, 데이터는 AWS S3에만 둔다.)
- **CNAPP** — CSPM·CIEM·취약점·KSPM·데이터 보안·attack-path를 하나의 그래프로 묶어, 단일 도구로는 못 잡는 **독성 조합(toxic combination)**을 탐지한다.
- **Agentic AI** — 질문해야 답하는 챗봇이 아니라, 에이전트가 read-only API를 스스로 호출(tool use)해 증거를 모으고 가설→증거→판정 루프로 위험을 추론한다.

---

## 주요 기능

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

## 기술 스택

영역별로 사용하는 주요 기술은 다음과 같다.

| 영역 | 사용 기술 |
|---|---|
| **AWS 보안** | CloudTrail, Config, Security Hub, Prowler, Inspector, IAM Access Analyzer, Macie(S3 민감데이터 전용) |
| **Azure 보안** | Microsoft Entra ID(신원·CIEM 핵심), Defender for Cloud(리소스 secure score) — *데이터 저장소 아님* |
| **워크로드 / 배포** | EKS, ECR, ArgoCD(GitOps), IRSA |
| **Shift-Left** | GitHub Actions(OIDC), Checkov / OPA, Trivy, kube-bench |
| **에이전틱 AI** | Amazon Bedrock(멀티에이전트), 수동 RAG, pgvector(RDS PostgreSQL t3.micro) |
| **수집 / 오케스트레이션** | EventBridge, SQS, Lambda, Step Functions, OCSF 정규화 |
| **인증** | Microsoft Entra ID(IdP) → Cognito → ALB(authenticate-oidc) |
| **관제 앱 (프론트)** | Vite + React + TypeScript, TanStack Query, Tailwind, React Flow(attack-path 그래프), Recharts(점수), MSW(mock 하네스) |
| **관제 앱 (백엔드)** | TypeScript Lambda (findings 읽기 API) — *폴리글랏: console=TS / engine·pipeline=Python* |
| **관측 / 호스팅** | S3 + CloudFront, kube-prometheus-stack |
| **IaC** | Terraform |

---

## 🏗️ 폴더 구조

> 마커: ✅ 내용 있음(구현/스캐폴드) · 📁 빈 폴더(자리 확보) · ⬜ 아직 미생성(계획).

```
cnapp-agentic/
├── CLAUDE.md                 ✅ 작업 기준 · 협업 규칙 · 변경 로그(읽기 우선)
├── README.md                 ✅
├── troubleshooting.md        ✅ 작업 로그 (트러블슈팅 + 진행, [영역] 태그)
├── cnapp-architecture.svg    ✅ 아키텍처 다이어그램
├── .github/workflows/        ✅ CI — contracts 정합 게이트(contracts-validate.yml, validate.py 4-assert)
├── contracts/                ✅ ★공유 이음새 계약(7종 JSON Schema) + control-catalog(14종) + 골든 mock 3종 + validate.py
├── docs/                     ✅ 설계 SSOT — project-draft · target-app-design · console-app-design · manual-infra
├── apps/
│   ├── target/               ✅ 취약 타깃 앱 (product · order · member[Python] + PII seeder) — 코드만
│   └── console/              ✅ 관제 앱 (Vite+React+TS, 8화면 MSW 목업 동작) — 코드만
├── engine/                   📁 공유 에이전틱 엔진 — core / triage·evidence / hypothesis·reasoning
├── scanners/                 ⬜ cspm · workload 스캐너 연동 — 코드만
├── pipeline/                 ⬜ ingest(EventBridge→SQS) · normalize(Lambda→OCSF) — 코드만
├── rag/                      ⬜ corpus·임베딩 적재 · retrieval·검색 — 코드만
├── attackpath/               ⬜ 상관 모델 · R1~R5 상관 로직 — 코드만
└── infra/                    Terraform (레이어드) — shared 먼저 → target · console · 영역별
    ├── shared/               ✅ VPC·NAT·EKS·ECR·RDS pgvector·OIDC·IAM (main.tf 스캐폴드, validate 통과)
    ├── target/               ✅ 취약 워크로드 + 의도적 결함 IaC(f3·f4·f6 var.enable_* 토글)
    ├── console/              📁 S3+CloudFront·ALB·Cognito·console-backend·SFn
    └── {scanners,pipeline,…} ⬜ 영역별 terraform(영역 주인이 apply)

# 컴포넌트 폴더(scanners·pipeline·engine·rag·attackpath)는 코드만 — 배포는 CI가 infra/에서 apply.
# 폴더는 사람이 아니라 컴포넌트로 나눔(소유·이음새는 docs/project-draft 4.6).
```

---

## 👥 역할 분담 (2인)

> 원칙 — 일을 나누되 **둘 다 상대 영역까지 이해**한다. 각 영역을 반반 갈라 양쪽이 핵심을 다 만진다. 상시 협의로 조정되는 살아있는 분담이며, **SSOT는 [CLAUDE.md §5](CLAUDE.md) · [project-draft §4.1](docs/project-draft.md)**.

| 영역 | 준형 | 진우 |
|---|---|---|
| **앱** | **타깃 앱 + 관제 앱 (2개 모두 전담)** | — |
| **토대** | CI/CD · Shift-Left · **공유 인프라 주도** | 모니터링 · 운영관제 · 추적 (Grafana · CloudTrail) |
| **스캐너 — CSPM** | Config · Prowler · Security Hub · Macie(AWS S3) | 워크로드 — Inspector · Trivy · kube-bench · Defender(Azure) |
| **스캐너 — CIEM** | IAM Access Analyzer (AWS) | Entra ID (Azure — Prowler `entra_id_*`) |
| **수집 · 정규화** | 수집부 (EventBridge→SQS) | 정규화부 (Lambda→OCSF) |
| **엔진 (Bedrock)** | Evidence(tool use) · Triage | Hypothesis · Reasoning · Orchestrator |
| **RAG** | 코퍼스 · 임베딩 · pgvector 적재 | 검색 · LLM 답변 생성 |
| **attack-path** | 그래프 데이터 모델 | 상관 로직 · 내러티브 |

> ⚠️ "관제"는 두 가지 — **관제 "앱"**(CNAPP 보안 대시보드 제품) = 준형 / **운영 "관제"**(Grafana·CloudTrail 플랫폼 관측) = 진우. 애플리케이션 2개는 모두 준형이 개발한다.

---

## 🚧 구현 현황 (Status)

| 영역 | 상태 |
|---|---|
| **공통 계약 (`contracts/`)** | ✅ **졸업** — 계약 7종 JSON Schema + INTERNAL control 카탈로그(14종) + 골든 시나리오 mock(findings·attack-path·case). `validate.py` 4-assert + GitHub Actions CI 게이트로 정합 보장 |
| **공유 인프라 (`infra/shared`)** | ✅ **스캐폴드** — VPC·NAT Instance·EKS(spot·IRSA)·ECR·RDS pgvector·GitHub OIDC·Evidence/Bedrock IAM. `terraform validate` 통과. apply는 게이트(state 버킷·Bedrock 모델 액세스·Azure 테넌트) 후 |
| **앱 2개 구현 청사진** | ✅ **완료** — 관제 앱(console §15: 스택·API 표면·화면↔mock)·타깃 앱(target §7: 결함↔IaC 토글) 청사진 확정. **앱 2개 모두 준형 전담** |
| **관제 콘솔 (`apps/console`)** | ✅ **8화면 목업 동작** — Vite+React+TS+Tailwind+TanStack+React Flow+MSW. 대시보드·Findings·Finding상세(Evidence 탭)·Attack-path + 조치·컴플라이언스·감사로그·로그인. MSW가 `contracts/mock-*.json` 서빙 → 백엔드·AWS 0으로 동작. `tsc`·`vite build` 통과. 다음 = (엔진 나오면) 실데이터 스왑 |
| **타깃 앱 (`apps/target`)** | ✅ **member 서비스 실행 + shop 포털** — member(Python/FastAPI) 회원 REST + **PII seeder**(faker→S3, Macie 미끼) + `/` 포털(product·order·member 소개). product/order는 결함 매니페스트(f1·f2·f5). 모든 PII/시크릿 가짜 |
| **결함 IaC (`infra/target`)** | ✅ **스캐폴드** — 공개 S3(f6)·열린 SG(f3)·과도 IRSA(f4) `var.enable_*` 토글(기본 off), remote_state로 infra/shared 참조. `terraform fmt` 통과 |
| TF state 부트스트랩 | ✅ `cnapp-agentic-tfstate` 버킷(manual-infra §2) |
| 스캐너 · 수집/정규화 · 엔진 · RAG · console-backend | ⬜ **예정** — 실데이터 파이프라인(Phase 3~) |

> **전략 = 계약·목업 우선.** 실제 스캐너/엔진을 기다리지 않고 `contracts/mock-*.json`으로 관제 콘솔·엔진을 끝까지 만든 뒤 실데이터로 교체 — 직렬 의존을 두 병렬 트랙으로 분리한다.

---

## 상세 설계

설계의 배경·결정 근거·로드맵 등 상세 내용은 상단 [📂 docs 안내](#-이-레포는-무엇인가--docs-안내) 표의 문서를 참고한다. (project-draft → target-app-design → console-app-design 순)

---

*변경 요약: Azure 역할을 데이터→신원(Entra ID) 중심으로 전환 — 데이터(회원 PII)는 AWS S3 전용·Macie도 S3 전용, Azure는 Entra CIEM + Defender secure score. 크로스클라우드 attack-path를 "AWS 워크로드→Azure 신원 장악" 경로로 갱신. README 상단에 레포 소개·docs 안내 추가.*

*변경 요약(2): 폴더 구조를 실제 구조(`contracts`·`scanners`·`pipeline`·`rag`·`attackpath`·`troubleshooting.md`)로 갱신 — 컴포넌트 단위 분리·terraform 레이어드 반영(docs/project-draft 4.6과 정합).*

*변경 요약(3): 구현 진입 반영 — 상단 상태 갱신 + **구현 현황(Status) 표 신설**(contracts 졸업·infra/shared 스캐폴드·CI 게이트), 폴더 트리에 `.github/workflows` 추가.*

*변경 요약(4): 앱 개발 진입 반영 — 앱 2개 구현 청사진(console §15·target §7) 완료 + **앱 2개 모두 준형 전담** 확정, 다음 착수 = `apps/console` 스캐폴딩. 기술 스택 표에 확정된 관제 앱 프론트/백엔드 스택(Vite+React+TS·TanStack·React Flow·MSW)·폴리글랏(console=TS/engine·pipeline=Python) 반영, docs 안내에 각 앱 구현 청사진 절 표기. **폴더 구조 트리를 실제 디스크 상태로 갱신** — 상태 마커(✅ 내용 있음 / 📁 빈 폴더 / ⬜ 미생성) 도입, `infra/` 하위(shared·target·console) 전개, `cnapp-architecture.svg` 추가, 미생성 컴포넌트 폴더(scanners·pipeline·rag·attackpath) 구분 표기.*

*변경 요약(5): 구현 진행 반영 — `apps/console` 골격 스캐폴드 완료(🔨, 빌드 통과)·TF state 부트스트랩(✅ `cnapp-agentic-tfstate`)를 상단 상태·Status 표·폴더 트리에 반영. 파비콘(cross-cloud attack-path 모티프 SVG) 추가.*

*변경 요약(6): 구현 진척 반영 — 관제 콘솔 **8화면 목업 동작**(스텁 4화면 완성), 타깃 앱 **member 실행 + shop 포털**(product·order·member 소개·네비), 결함 IaC(`infra/target`) 토글을 상단 상태·Status 표에 갱신. 관제 앱 파비콘을 **밝은 방패**로, 타깃 앱은 **쇼핑백 파비콘** 신설. 인트로 "현재 단계" 문구를 최신화하고 "SSOT 정합"→"설계 문서·공통 계약 정합"으로 명확화.*
