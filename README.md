# 에이전틱 AI 기반 멀티클라우드 CNAPP 보안 플랫폼

> 멀티클라우드(AWS 워크로드 + Azure 신원·데이터) 환경의 설정부터 워크로드·IaC 코드까지 **code-to-cloud 보안 위험을 점검·통합·상관분석**하고, 그 위에 **에이전틱 AI(Bedrock 멀티에이전트 + RAG)**로 발견 항목을 설명·우선순위화·자동 개선하는 CNAPP형 보안 플랫폼.

---

## 핵심 키워드

- **Multi-Cloud** — AWS(워크로드의 주인)와 Azure(신원·데이터의 주인)의 흩어진 보안 상태를 OCSF로 정규화해 단일 뷰로 통합하고, 클라우드 경계를 넘는 위험 경로를 추적한다.
- **CNAPP** — CSPM·CIEM·취약점·KSPM·데이터 보안·attack-path를 하나의 그래프로 묶어, 단일 도구로는 못 잡는 **독성 조합(toxic combination)**을 탐지한다.
- **Agentic AI** — 질문해야 답하는 챗봇이 아니라, 에이전트가 read-only API를 스스로 호출(tool use)해 증거를 모으고 가설→증거→판정 루프로 위험을 추론한다.

---

## 주요 기능

- **6기둥 CNAPP 점검** — CSPM(설정), CIEM(권한), 취약점, KSPM(쿠버네티스), 데이터 보안(DSPM 맛), attack-path를 통합 점검.
- **에이전틱 AI 분석** — finding 자동 설명(근거·조치법 카드), 위험 우선순위 자동 정렬, attack-path 내러티브 생성, 그리고 read-only tool use로 증거를 능동 수집.
- **크로스클라우드 attack-path** — "AWS 취약 워크로드 침투 → 과도 권한 측면 이동 → 공개 S3의 PII 탈취 → Azure 민감 데이터 노출"처럼, 개별적으로는 중간 위험인 finding들을 하나의 탈취 경로로 엮어낸다.
- **Shift-Left CI 게이트** — PR 단계에서 Checkov/OPA(IaC 미스컨피그)와 Trivy(이미지 CVE)로 검사해, 위험한 변경이 프로덕션에 가기 전에 차단한다.
- **휴먼인더루프 자동 개선** — 에이전트는 기본적으로 조회만 수행하고, 변경(remediation)은 승인 경로를 통해서만 적용하며 모든 판정·조치를 불변 감사로그로 남긴다.

---

## 아키텍처 개요

```
[ 입력: CNAPP 신호 ]
  AWS 설정/워크로드 :  Config · Security Hub · Prowler · Inspector · Trivy · kube-bench · IAM Access Analyzer · Macie
  AWS 빌드 게이트   :  CI에서 Checkov/OPA(IaC) · Trivy(이미지)
  Azure            :  Defender for Cloud · Entra ID(CIEM) · Storage 점검
        │  (ASFF / OCSF 정규화)
        ▼
  EventBridge → SQS → Lambda
        │
  ┌──── 공유 에이전틱 엔진 (Bedrock 멀티에이전트 + RAG) ────┐
  │  Orchestrator → Triage → Hypothesis → Evidence → Reasoning │
  │  거버넌스: 최소권한 · read-only first · 불변 감사로그       │
  └────────────────────────────────────────────────────────────┘
        │
  [ attack-path 그래프 ]  권한 + 취약점 + 설정 + 데이터 → 탈취 경로(크로스클라우드)
        │
  위험 → 자동 개선 제안 → 휴먼인더루프(승인) → Step Functions → 감사로그
        │
  [ 관제 앱 ]  posture 점수 + findings + attack-path + AI 설명/조치  (React · S3+CloudFront)
```

**연결 구조 (agentless):** 점검 대상인 타깃 앱은 클라우드 계정에 *배포*만 되고, 스캐너가 계정을 외부에서 **read-only로 스캔**한다. findings는 수집 파이프라인을 거쳐 정규화·저장되며, 관제 앱은 그 저장소를 읽어 표시한다. 타깃 앱과 관제 앱 사이의 직접 통신은 없다.

---

## 기술 스택

| 영역 | 사용 기술 |
|---|---|
| **AWS 보안** | CloudTrail, Config, Security Hub, Prowler, Inspector, IAM Access Analyzer, Macie |
| **Azure 보안** | Defender for Cloud, Microsoft Entra ID, Storage |
| **워크로드 / 배포** | EKS, ECR, ArgoCD(GitOps), IRSA |
| **Shift-Left** | GitHub Actions(OIDC), Checkov / OPA, Trivy, kube-bench |
| **에이전틱 AI** | Amazon Bedrock(멀티에이전트), 수동 RAG, pgvector(RDS/Aurora PostgreSQL) |
| **수집 / 오케스트레이션** | EventBridge, SQS, Lambda, Step Functions, OCSF 정규화 |
| **인증** | Microsoft Entra ID(IdP) → Cognito → ALB(authenticate-oidc) |
| **프론트 / 관측** | React, S3 + CloudFront, kube-prometheus-stack |
| **IaC** | Terraform |

---

## 폴더 구조

```
cnapp-agentic/
├── docs/        설계 문서 (단일 진실 공급원)
├── apps/
│   ├── target/  취약 타깃 앱 (커머스 마이크로서비스 — findings 소스)
│   └── console/ 관제 앱 (posture·findings·attack-path 대시보드)
├── engine/      공유 에이전틱 엔진 (Bedrock 멀티에이전트 + RAG + OCSF 정규화)
└── infra/       Terraform IaC (shared / target / console)
```

---

## 상세 설계

설계의 배경·결정 근거·로드맵 등 상세 내용은 다음 문서를 참고한다.

- [docs/project-draft.md](docs/project-draft.md) — 메인 설계서 (방향·범위·아키텍처·로드맵)
- [docs/target-app-design.md](docs/target-app-design.md) — 타깃 앱 상세 (결함 목록·골든 attack-path)
- [CLAUDE.md](CLAUDE.md) — 작업 기준 및 협업 규칙

> 본 프로젝트는 클라우드 보안 엔지니어 포트폴리오 목적의 2인 협업 개인 프로젝트입니다.
