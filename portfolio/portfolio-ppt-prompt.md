# 포트폴리오 PPT 생성 프롬프트 (취업 지원용 · 15장)

> 이 문서를 Gamma·Copilot·Claude 등 AI 슬라이드 툴에 그대로 붙여넣으면 포트폴리오 PPT를 재생성할 수 있다.
> 초안 pptx(`portfolio-cnapp-agentic.pptx`)와 동일한 구성. 수치·사실은 2026-07-03 기준 레포(README·CLAUDE.md) 정합.

---

## 프롬프트 (아래 전체를 복사해서 사용)

클라우드 보안 엔지니어 취업 지원용 포트폴리오 발표 자료를 만들어줘. 한국어, 15장, 다크 네이비+시안 계열의 기술적이고 깔끔한 톤. 슬라이드당 텍스트는 핵심만(3~5개 불릿), 발표 보조용.

**프로젝트:** "에이전틱 AI 기반 멀티클라우드 CNAPP 보안 플랫폼" (cnapp-agentic)
- 2인 협업 개인 프로젝트, 역할: 이준형 — 앱 2개(취약 타깃 앱·관제 콘솔) 개발, 공유 인프라(Terraform 6층) 주도, CI/CD·Shift-Left, 엔진 Evidence(tool use)·Triage, CSPM 스캐너, 수집부, RAG 코퍼스·pgvector, attack-path 그래프 모델
- 한 줄: AWS(워크로드)+Azure(신원, Entra ID) 멀티클라우드의 code-to-cloud 보안 위험을 점검·정규화(OCSF)·상관분석하고, Bedrock 에이전틱 AI + RAG로 설명·우선순위화·자동 개선하는 CNAPP 플랫폼

**슬라이드 구성 (15장):**

1. **표지** — 프로젝트명, "AWS 워크로드 × Azure 신원 — 크로스클라우드 공격경로를 스스로 조사하는 보안 플랫폼", 이름·기간(2026.06~진행중)·2인 협업
2. **문제 정의** — 멀티클라우드에서 보안 신호가 도구별로 파편화됨 / 개별 finding은 중간 위험이라 우선순위에서 밀림 / 진짜 위험은 '독성 조합(toxic combination)' — 조합이 만드는 공격경로는 단일 도구로 못 잡음 / 기존 AI 보안은 "물어봐야 답하는 챗봇" 수준
3. **솔루션 개요 — 핵심 키워드 3개** — ① Multi-Cloud: AWS=워크로드의 주인, Azure=신원의 주인(Entra ID), OCSF 정규화로 단일 뷰 ② CNAPP: CSPM·CIEM·취약점·KSPM·데이터·attack-path 6기둥 통합 ③ Agentic AI: 챗봇 탈출 — LLM이 read-only API를 스스로 호출(tool use)해 증거 수집, 가설→증거→판정 루프
4. **전체 아키텍처** — 흐름도: 스캐너(Config·Security Hub·Prowler·Trivy·Macie·Entra CIEM·Defender) → OCSF 정규화 → EventBridge→SQS→Lambda → 에이전틱 엔진(Bedrock)+pgvector RAG → attack-path 그래프 → HITL 자동조치(Step Functions) → 관제 콘솔(React). agentless 구조(타깃 앱↔관제 앱 직접 통신 없음, read-only 스캔)
5. **골든 시나리오 — 크로스클라우드 신원 탈취 attack-path** — 4단계 체인: ① 취약 이미지(KEV CVE)로 워크로드 침투 → ② 과도 IRSA + 평문 시크릿에서 Azure SP 자격증명 발견 → ③ 공개 S3에서 회원 PII 탈취 → ④ 탈취 자격증명으로 Azure Entra ID 과도권한 앱 장악. 개별로는 중간 위험 finding 들이 하나의 Critical 경로로 상관(상관규칙 R1~R5, 체인 길이≥3이면 Critical 격상)
6. **에이전틱 엔진 — 5단계 능동조사 루프** — Orchestrator → Triage(게이트: severity 높거나 attack-path 소속만 승급 = 비용 통제 내재화) → Hypothesis(가설 생성) → Evidence(★핵심: LLM이 Bedrock tool use로 read-only API를 스스로 선택·호출, allowlist 2중 강제) → Reasoning(한국어 내러티브·판정·권고)
7. **하이라이트 — 실환경 검증 완료** — 실 Bedrock Claude Haiku가 스스로 s3:GetBucketPolicy·GetPublicAccessBlock을 선택 호출 → 실제 공개 S3 버킷의 실 API 응답으로 판정 CONFIRMED(100%) → 즉시 destroy(비용 ~$0). "AI가 스스로 증거를 모은다"가 목업이 아닌 실동작임을 증명. end-to-end 러너로 스캐너→정규화→상관→엔진→RAG 한 줄 관통도 검증
8. **계약 기반 설계 (contracts = SSOT)** — 컴포넌트 이음새를 JSON Schema 7종(finding·case·attack-path·evidence-allowlist·수집 봉투·rag-chunk 등) + control 카탈로그 14종 + 골든 mock으로 먼저 고정 → 2인이 직렬 의존 없이 병렬 개발, mock↔실물 스왑이 매끄러움. validate 스크립트 + GitHub Actions CI 게이트로 정합 상시 보장
9. **관제 콘솔** — Vite+React+TS+Tailwind, 8화면(대시보드·Findings·Finding 상세[Evidence 탭=AI 능동조사 과정 표시]·Attack-path[React Flow, AWS/Azure 레인]·조치·컴플라이언스(ISMS-P)·감사로그·로그인), MSW mock→실 API 무변경 스왑, RBAC(viewer/approver), SSO: Entra ID(SAML)→Cognito→ALB
10. **취약 타깃 앱 & 결함 IaC** — 쇼핑몰 마이크로서비스(product·order·member) EKS 배포, 취약점은 앱 코드가 아니라 IaC에 의도적으로 심음(공개 S3·열린 SG·과도 IRSA 등 Terraform 토글, 기본 off), PII는 faker 합성 데이터(Macie 미끼), 모든 시크릿 가짜
11. **보안 거버넌스** — read-only first(에이전트 기본 조회만) / 변경은 HITL 승인 경로(Step Functions) 분리 + 격상 역할 / 불변 감사로그(S3 Object Lock) / 키리스 인증(GitHub OIDC·IRSA, 장기 자격증명 0) / 조치 실행기 3종(S3 공개차단·SG 개방 인바운드 제거·IAM 최소권한 diff)
12. **FinOps — 비용을 설계 원칙으로** — mock-first로 빌드 기간 대부분 AWS $0 / apply→test→destroy 규율(월 과금→시간 과금) / 경량 대체: NAT Instance(월 ~$32→~$3)·RDS t3.micro+pgvector(OpenSearch 대체)·Karpenter spot / 모델 티어링(Haiku/Sonnet)+Triage 게이트로 토큰 비용을 소수 케이스에 한정 / 트레이드오프를 정직하게 문서화
13. **CI/CD & 협업** — GitHub Actions CI(mock 회귀 10종+e2e+계약 검증 하드 게이트, Trivy·Checkov Shift-Left) / ArgoCD GitOps CD + Karpenter·HPA / 2인 협업: 설계 문서 SSOT·변경 로그·독립 리뷰 에이전트로 상호 검증(실버그 다수 사전 발견)
14. **현황 & 로드맵** — 완료: 전 영역 mock 동작(engine·attackpath·pipeline·rag·scanners), 앱 3종(타깃·콘솔 프론트/백엔드), Terraform 6층 validate 통과, DB 스키마·Lambda 핸들러, 엔진 실 tool-use 검증 / 다음: 단계별 실 apply(apply→검증→destroy), 실 스캐너 finding 관통, SSO 라이브, 데모 시나리오 완성
15. **마무리 — 배운 점** — 계약 우선 설계가 협업·비용·일정을 동시에 푼다 / 비용 제약이 아키텍처를 더 깨끗하게 만든다(AWS=워크로드/Azure=신원 역할 분리) / "에이전틱"의 단일 기준 = LLM의 능동 tool use를 실검증으로 증명 / 감사·승인·최소권한 등 거버넌스를 처음부터 내재화. + 레포/연락처

**디자인 지침:** 다크 네이비 배경 + 시안/보라 포인트, 아키텍처·시나리오 슬라이드는 다이어그램 중심, 코드/터미널 느낌 요소 활용, 이모지 최소화, 폰트는 고딕 계열.
