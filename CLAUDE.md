# CLAUDE.md

> 이 파일은 Claude Code(및 협업자)가 이 레포에서 작업할 때 가장 먼저 읽는 기준 문서다.
> 상세 설계는 [docs/project-draft.md](docs/project-draft.md)(메인 설계서 v5)와 [docs/target-app-design.md](docs/target-app-design.md)(타깃 앱 상세)에 있다. **이 둘이 단일 진실 공급원(SSOT)이며, 본 문서는 그 요약 + 협업 규칙이다.**

---

## 1. 한 줄 요약

멀티클라우드(AWS 워크로드 + Azure 신원·데이터) 환경의 설정(Posture)부터 워크로드·IaC 코드까지 **code-to-cloud 보안 위험을 점검·통합·상관분석**하고, 그 위에 **에이전틱 AI(Bedrock 멀티에이전트 + RAG)**로 발견 항목을 설명·우선순위화·자동 개선하는 **CNAPP형 보안 플랫폼**.

---

## 2. 핵심 키워드

- **Multi-Cloud** — AWS(워크로드의 주인) + Azure(신원·데이터의 주인). 흩어진 보안 상태를 OCSF로 정규화해 단일 뷰로 통합하고, **AWS 침해가 Azure 신원·데이터로 번지는 크로스클라우드 attack-path**까지 추적.
- **CNAPP** — CSPM·CIEM·취약점·KSPM·데이터(DSPM 맛)·attack-path 6기둥. CSPM을 넓히지 않고 **워크로드(코드 방향)로 깊게** 심화. SOC(실시간 위협탐지/대응)는 범위 밖(확장 훅만).
- **Agentic** — 챗봇이 아니라 에이전트가 능동적으로 일한다. **챗봇 탈출의 단일 기준 = LLM이 read-only API를 스스로 호출해 증거를 모으는가(tool use).** Orchestrator → Triage → Hypothesis → Evidence → Reasoning 루프(가설→증거→판정).

---

## 3. 핵심 설계 결정 (요약)

상세·근거는 설계서 11번. 가장 자주 부딪히는 결정만 추림:

| 결정 | 요점 |
|---|---|
| **단일 계정 / 단일 리전(서울)** | Organizations·Identity Center·Control Tower **절대 안 켬**(무료 크레딧 소멸 트리거). CloudTrail/Config는 전 리전 수집. |
| **키 없는 인증** | CI/CD는 GitHub OIDC→IAM Role, 파드는 IRSA/Pod Identity. 장기 자격증명 미사용. |
| **EKS + ArgoCD GitOps** | 워크로드 운영·배포의 핵심 축. |
| **앱 2개** | ① 취약 타깃 앱(findings 소스) ② 관제 앱(HALO의 NOVA 대응, 얼굴). **둘은 직접 통신 안 함 — agentless.** |
| **취약점은 IaC에 심음** | 앱 코드 버그가 아니라 인프라/설정 결함. 기능 최소, 결함 다양성 최대. |
| **Bedrock + 수동 RAG** | SageMaker 미사용. 벡터DB = **pgvector(RDS/Aurora PostgreSQL)** 확정(코퍼스 작아 OpenSearch는 오버스펙). |
| **앱 SSO = Cognito 허브** | Entra ID(IdP) ─SAML→ Cognito ─OIDC→ ALB(authenticate-oidc). 워크포스 SSO 크레딧 회피. |
| **Azure는 Defender for Cloud로 점검** | Security Hub는 AWS 전용. Prowler로 멀티클라우드 병행. |
| **Read-only first + HITL** | 에이전트는 기본 조회만. 변경(remediation)은 분리된 승인 경로(Step Functions) + 불변 감사로그(S3 Object Lock). |

**연결 구조(꼭 기억):** 타깃 앱은 AWS/Azure에 *배포*만 됨 → 스캐너가 계정을 **read-only로 스캔** → findings → EventBridge→SQS→Lambda → OCSF 정규화 → pgvector/엔진 → 관제 앱이 findings 저장소를 **읽어서** 표시. 타깃 앱↔관제 앱 직접 API 없음.

---

## 4. 폴더 구조

```
cnapp-agentic/
├── CLAUDE.md                 # 이 문서 — 작업 기준 + 협업 규칙
├── README.md
├── docs/                     # ★ 설계 SSOT (변경 시 반드시 여기 먼저 반영)
│   ├── project-draft.md      #   메인 설계서 v5 (방향·범위·아키텍처·로드맵)
│   └── target-app-design.md  #   타깃 앱 상세 (결함 목록·골든 attack-path)
├── apps/
│   ├── target/               # 취약 타깃 앱 (커머스 3 마이크로서비스: product/order/member). findings 소스
│   └── console/              # 관제 앱 (React, posture·findings·attack-path·AI 설명/조치)
├── engine/                   # 공유 에이전틱 엔진 코어 (Bedrock 멀티에이전트 + RAG + OCSF 정규화)
└── infra/                    # Terraform IaC
    ├── shared/               #   공유 골격 (계정·VPC·EKS·인증·수집 파이프라인·벡터DB)
    ├── target/               #   타깃 앱 인프라 (★ 의도적 결함을 IaC에 심는 곳)
    └── console/              #   관제 앱 인프라 (S3+CloudFront·ALB·Cognito·Step Functions)
```

> 폴더 경계(모노레포 vs 멀티레포, Terraform 모듈 경계, 공유 코어 위치)는 설계서 24번 "미확정"에 일부 열려 있음. 구조를 바꿀 땐 docs에 먼저 반영.

---

## 5. 작업 분담 (효율용 트랙)

> **원칙:** 다른 환경에서 병렬 작업하려고 일을 나누되, **둘 다 상대 영역까지 완전히 이해**한다. 분담은 효율 수단이지 분리 소유가 아니다.

| | **트랙 1** | **트랙 2** |
|---|---|---|
| **새 역량** | CI/CD · GitOps · Shift-Left | 관측 · Grafana · 로그 파이프라인 |
| **보안 영역** | **CSPM 본체 + Shift-Left CI 게이트** | **워크로드(취약점·KSPM) + CIEM + attack-path 그래프** |
| **핵심 기술** | GitHub Actions·OIDC·ArgoCD, Checkov/Trivy(CI), Config·Security Hub CSPM·Prowler | Inspector·Trivy(런타임)·kube-bench, IAM Access Analyzer, kube-prometheus-stack·로그 |

**공유 자산(양쪽 함께):** 수집 파이프라인(EventBridge→SQS→Lambda, OCSF 정규화), 에이전틱 엔진 코어(`engine/`), 인프라 골격(`infra/shared/`), 관제 대시보드(`apps/console/`).

---

## 6. 협업 규칙

1. **작업 시작 전 `git pull`** — 항상 최신 main을 받고 시작. 충돌 줄이기.
2. **작업 후 `commit` + `push`** — 의미 단위로 커밋하고 바로 push해 상대가 받을 수 있게. 커밋 메시지는 `타입: 내용`(예: `feat: ...`, `docs: ...`, `infra: ...`).
3. **설계 변경은 docs에 먼저 반영** — 방향·범위·구조·결정이 바뀌면 [docs/project-draft.md](docs/project-draft.md) 또는 [docs/target-app-design.md](docs/target-app-design.md)를 **먼저** 업데이트하고, 영향이 있으면 본 CLAUDE.md도 갱신. 코드/문서 불일치를 남기지 않는다.
4. **무료 티어 가드레일 준수** — Organizations/Identity Center/Control Tower 금지. 종량제 서비스(Config·Security Hub·Inspector·Macie·Defender)는 데모 기간만 켜고 `destroy`. Budgets 알림 유지.
5. **보안 기본** — 장기 키 커밋 금지(OIDC/IRSA 사용), 시크릿은 Secrets Manager+KMS. 에이전트는 read-only first, 변경은 HITL 승인 경로로만.

---

## 7. 앞으로의 작업 기준

- **모든 작업은 `docs/`와 이 `CLAUDE.md`를 기준으로 진행한다.** 새 기능·결정·구조 변경은 먼저 설계 문서와 정합성을 확인하고, 어긋나면 문서를 갱신한 뒤 코드를 작성한다.
- 우선순위 컷라인(설계서 21번): **① 절대사수** = CSPM 본체 + RAG 설명 + 대시보드 + Azure 통합 + Shift-Left + KSPM, **② 보너스** = 공급망 서명·attack-path 정교화·ISMS-P 리포트, **③ 확장** = CWPP 런타임·SOC.
- 미확정 항목(설계서 24번)은 결정될 때마다 docs에 반영하고 여기 요약을 갱신한다.
