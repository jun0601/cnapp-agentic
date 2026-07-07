# 관제 콘솔 사용 매뉴얼 (Console App Manual)

> **이 문서는 무엇인가:** 관제 앱(`apps/console`)을 **어떻게 쓰는가**를 화면별로 설명하는 사용 설명서다.
> 설계 근거·데이터 스키마·API 계약은 [console-app-design.md](console-app-design.md)(설계 SSOT), 전체 방향은 [project-draft.md](project-draft.md)를 본다.
> **이 문서 = "무엇을 보고 무엇을 누르나" / 설계서 = "왜·어떻게 만들었나".**

- **접속:** https://cnapp-agentic.cloud (인프라가 apply된 상태일 때)
- **로그인:** Microsoft Entra ID SSO — `jh_lee@cnappagentic.onmicrosoft.com`(APPROVER) · `jw_kim@…`(viewer)
- **성격:** 읽기 우선(read-only first). 실제 변경(조치)은 승인(HITL) 경로로만. 타깃 앱과 **직접 통신하지 않음**(agentless).

---

## 0. 한눈에 — 이 앱이 하는 일

멀티클라우드(**AWS=워크로드 / Azure=Entra 신원**)에 흩어진 보안 발견사항(findings)을 한 화면에 모아, 그 위에 **에이전틱 AI**로 설명·우선순위화·조치까지 잇는 CNAPP 관제 화면이다. 핵심 차별점 3가지:

1. **크로스클라우드 attack-path** — AWS 워크로드 침해가 Azure Entra 신원 장악으로 번지는 공격 경로를 그래프로 추적.
2. **AI 능동조사(챗봇 탈출)** — LLM이 스스로 read-only API를 호출해 증거를 모으고 판정한다. 질문에 답만 하는 챗봇이 아니다.
3. **RAG 지식베이스** — 보안 지식을 pgvector(임베딩)로 검색해 근거와 함께 자연어로 답한다.

---

## 1. 접속 · 로그인 · 역할(RBAC)

### 1.1 로그인 흐름 (옵션 B: SPA가 Cognito로 직접 OIDC)
```
https://cnapp-agentic.cloud 접속
  → 자동으로 로그인 화면(/login)
  → "Microsoft Entra ID로 로그인" 클릭
  → Cognito Hosted UI → Entra ID(조직 계정 인증)
  → 콜백(/callback)에서 토큰 교환
  → 대시보드 입장 (우상단에 이메일·역할 표시)
```
> 로그인 화면 하단에 이 3단계(Entra → Cognito → SPA)가 그림으로 표시된다.

### 1.2 역할(2종) — 무엇을 할 수 있나
| 역할 | 조회 | AI 재조사 | 조치 승인/거부 |
|---|:---:|:---:|:---:|
| **viewer**(분석가) | ✅ 모든 화면 | ❌ | ❌ |
| **approver**(보안관리자) | ✅ 모든 화면 | ✅ | ✅ |

- 역할은 **Entra 그룹(GUID) → Cognito `custom:groups` → 토큰**으로 자동 판정된다. 화면에서 고르는 게 아니다.
- `jh_lee@`가 `cnapp-approver` 그룹 소속 → **APPROVER**. 그 외는 viewer.
- (개발/목업 모드에서만) 헤더에 역할 스위처가 보인다. 실데이터에선 숨겨진다.

---

## 2. 화면별 기능

상단 내비게이션 순서: **대시보드 · Findings · Attack-path · 🤖 AI 어시스턴트 · AI·시스템 · 조치 · 컴플라이언스 · 감사로그**

### 2.1 대시보드 (`/`) — 위험을 한눈에
첫 화면. 위에서 아래로:
- **KPI 카드 4개**: 전체 finding · Open · Critical(severity 1) · 공격 경로 수.
- **Secure Score**: AWS(주·크게) + Azure Entra/Defender(보조) 점수 막대. 멀티클라우드 80/20 비중.
- **기둥별 Open**: 6기둥(CSPM·CIEM·취약점·KSPM·데이터) 중 어디에 open이 몰렸는지 막대.
- **🛑 크로스클라우드 Attack-path 배너**: 상관된 공격 경로 요약(노드·엣지 수 + "AWS → Azure" 태그). **클릭하면 그래프 화면으로.**
- **우선순위 상위 finding**: AI 우선순위 상위 5건. 클릭 → 상세.

> **여기서 시작해서 배너를 누르면 데모의 핵심(공격 경로)으로 바로 진입한다.**

### 2.2 Findings (`/findings`) — 발견사항 목록
- **필터**: 기둥(CSPM/CIEM/취약점/KSPM/데이터) · 클라우드(AWS/Azure) · 상태(open/remediated/suppressed).
- **정렬**: AI 우선순위(기본) 또는 심각도.
- **새로고침** 버튼(수동) — 목록은 45초 주기로도 자동 폴링.
- 각 줄(**FindingCard**)이 보여주는 것: 좌측 심각도 컬러바 · 심각도 배지 · 클라우드(주황=AWS/파랑=Azure) · 기둥 · 제목 · resource_id · **🛑 경로 배지**(attack-path 연결 시) · **AI 상태**(완료/대기/실패) · 상태.
- 줄을 클릭 → **Finding 상세**.

### 2.3 Finding 상세 (`/findings/:id`) — ★AI가 드러나는 곳
상단에 finding 본문(심각도·클라우드·기둥·resource_id·control·sources·attack-path 링크). **본문은 AI가 죽어도 항상 표시**된다(AI 레이어와 분리).

**🤖 AI 재조사 버튼** (approver 전용): 누르면 백엔드가 오케스트레이터 Lambda를 비동기로 깨워 **실 Bedrock이 다시 조사**한다. "조사 시작됨" 표시 후 1~2분 뒤 자동 갱신. (viewer에겐 버튼이 안 보임 — Bedrock 비용이 드는 액션이라)

그 아래 **2개 탭**:

**① 💬 AI 설명 (UC1)** — 이 finding 하나에 대한 설명 카드 3장:
- 📌 요약 · ⚠️ 왜 위험한가 · 🛠️ 조치 방법.
- `ai_status`가 done이 아니면 "AI 분석 대기/실패" placeholder(스캐너 데이터는 정상).

**② 🔎 능동조사 (Evidence, UC0)** — **프로젝트의 심장**. 이 finding이 속한 조사 case를 렌더:
- **판정 히어로**: verdict(confirmed/refuted) + 신뢰도 % + "AI가 N회 read-only API를 **스스로 호출**해 증거 수집".
- **① 트리아지 게이트**: ESCALATE/HOLD + 사유(비용 통제 — escalate된 것만 조사).
- **② 가설(Hypothesis)**: AI가 세운 공격 가설 목록.
- **③ 능동 수집 증거 · 타임라인**: AI가 부른 read-only API를 **번호 스텝**으로(예: `s3:GetBucketPolicy` → 공개 버킷 확인). 이게 "챗봇 탈출"의 시각적 증거.
- **④ 판정(Reasoning)**: 최종 verdict + 내러티브 + 지식베이스 근거(control_id).
- **모델 추적**: 단계별 모델·토큰(비용 관측).

> **verdict가 refuted로 나올 수 있다** — 실 Bedrock이 실제 증거로 조사했는데 대상 리소스가 실제론 취약하지 않으면(타깃 결함 토글 off) 정직하게 refuted를 낸다. 이건 오류가 아니라 **진짜 조사한다는 증거**다.

### 2.4 Attack-path (`/attack-paths`) — 크로스클라우드 공격 경로
- **그래프(React Flow)**: 노드=리소스, 엣지=관계. **AWS 워크로드 / Azure 신원**을 시각적으로 구분하고, 경계를 넘는 **크로스클라우드 엣지(빨강)**를 강조.
- **범례**: AWS 노드(주황)·Azure 노드(파랑)·크로스클라우드 엣지(빨강)·내부 엣지(회색).
- **공격 서사(Reasoning)**: "공격자가 AWS 워크로드로 들어와 ~를 타고 **Azure Entra ID 신원까지 장악**"을 문장으로.
- 골든 시나리오: product 취약 이미지 침투 → order 과도 IRSA + 평문 Azure 시크릿 → member 공개 S3로 PII 탈취 → Azure Entra 과도권한 앱 장악.

### 2.5 🤖 AI 어시스턴트 (`/chat`) — RAG 자연어 질의
- 프리미엄 챗 UI(말풍선·타이핑·추천 질문).
- 동작: 질문 → **Titan 임베딩 → pgvector 코사인 유사도 검색(top-4) → Bedrock(Haiku) 답변**.
- 답변 아래 **근거(refs)**: 검색된 지식 청크의 `control_id` + 미리보기 스니펫. "어떤 지식으로 답했는지"를 보여준다.
- 헤더에 `Titan → pgvector → Bedrock` 파이프라인 pill 표시.
- 무료 크레딧 내 동작(Bedrock Haiku). 예: "S3 버킷이 공개되면 왜 위험하고 어떻게 조치해?"

### 2.6 AI·시스템 (`/system`) — AI가 어떻게 도는지 관측
"AI를 못 느끼겠다"는 갭을 메우는 관측 화면:
- **데이터 파이프라인 스트립**: 스캐너 → 수집 → 정규화 → 상관 → 트리아지 → **Evidence(AI tool-use)** → **Reasoning** → 콘솔.
- **Bedrock 사용량(24h)**: 모델 호출·입력/출력 토큰(CloudWatch AWS/Bedrock 실집계).
- **AI 모델 3종**: 능동조사 엔진(tool-use)·RAG 챗·임베딩 — 각 모델 ID와 역할.
- **RAG 지식베이스**: 청크 수·커버 control 종수·pgvector HNSW(코사인) — 실 RDS 통계.
- **데이터 현황**: findings(open/전체)·attack-path·AI 조사 case 수.
- **더 깊은 관측 안내**: CloudWatch 대시보드(`cnapp-agentic-platform`)·Grafana·감사로그.
- 우상단 배지: `LIVE`(실 RDS·CloudWatch 집계) 또는 `목업`.

### 2.7 조치 (`/remediation`) — HITL 승인 (approver)
- **자동 조치 카탈로그 MVP 3종**: S3 Public Access Block · SG 0.0.0.0/0 인바운드 제거 · IAM 최소권한 diff.
- 자동 조치 가능한 open finding만 **승인 대기 큐**에 노출.
- **approver만** 승인/거부 가능. 승인 → 백엔드가 **Step Functions StartExecution**(콘솔은 트리거만, 실행은 격상 역할) → 감사로그에 **불변 기록**.
- Azure findings는 자동 실행 없이 **조치 가이드**만.
- viewer면 "approver 권한 필요" 안내.

### 2.8 컴플라이언스 (`/compliance`) — ISMS-P 매핑
- **충족률(%)** + 충족/미충족 건수.
- 도메인별(인증·접근통제·암호화·로그·취약점·개인정보) 미충족 요약 카드.
- 항목별 상세 표: ISMS-P 기준 ↔ INTERNAL control 매핑 ↔ finding 수 ↔ 상태(충족/미충족/해당없음).
- PDF 내보내기는 보너스(UC5, 비활성).

### 2.9 감사로그 (`/audit`) — 불변 기록
- 모든 판정·조치·스캔·인증(로그인)을 **시간순**으로.
- 🔒 **불변(S3 Object Lock)** — 조회 전용.
- 액션 필터: 전체/승인/거부/판정/스캔/로그인/조회.
- 각 줄: 시각 · 행위자(사람/engine/scanner) · 액션 · 대상/결과.

---

## 3. AI는 어떻게 동작하나 (크라운주얼)

### 3.1 에이전틱 엔진 루프
```
Orchestrator
  → Triage(트리아지 게이트: 우선순위·비용 통제 — escalate된 것만 다음 단계)
  → Hypothesis(공격 가설 생성)
  → Evidence(★ 실 Bedrock이 read-only API를 스스로 골라 호출 → 증거 수집)
  → Reasoning(증거 기반 판정 + 내러티브 + 지식베이스 근거)
```
- **"챗봇 탈출"의 단일 기준 = LLM이 스스로 tool(API)을 호출해 증거를 모으는가.** Finding 상세의 Evidence 탭이 이 장면.
- Evidence가 부르는 API는 **allowlist(계약④)로 2중 강제** — LLM이 그 밖의 API를 못 고른다. 전부 **read-only**(조회만).

### 3.2 RAG(지식베이스)
- 보안 지식을 control 단위 청크로 → **Titan v2 임베딩(1024차원)** → pgvector 적재.
- 질의도 같은 Titan으로 임베딩 → **코사인 유사도**로 관련 청크 검색(HNSW 인덱스) → Bedrock이 그 근거로 답변.
- `/chat`(대화)과 Evidence 판정의 `지식베이스 근거`가 이 파이프라인을 쓴다.

---

## 4. 데이터는 어디서 오나 (agentless)

```
타깃 앱(AWS/Azure에 배포만) 
  → 스캐너가 계정을 read-only 스캔(kube-bench·Trivy·Prowler·Macie 등)
  → findings
  → EventBridge → SQS → Lambda → OCSF 정규화
  → 상관(attack-path) → 엔진(AI 조사) → pgvector(RDS)
  → [관제 콘솔이 이 저장소를 '읽어서' 표시]
```
- **타깃 앱 ↔ 관제 앱 직접 API 없음.** 콘솔은 findings 저장소를 읽기만 한다.
- 콘솔은 30~60초 주기 폴링 + 수동 새로고침으로 최신화한다.

---

## 5. 데모 시연 동선 (추천 흐름)

이 순서로 누르면 "위험 조망 → 공격 경로 → AI 조사 → 조치 → 관측"이 한 흐름으로 이어진다:

1. **대시보드** — 전체 위험·Secure Score를 보고, **🛑 크로스클라우드 attack-path 배너 클릭**.
2. **Attack-path** — 그래프에서 AWS→Azure 경계를 넘는 빨강 엣지 + 공격 서사 읽기.
3. **Findings → 상위 finding 클릭 → 🔎 Evidence 탭** — AI가 read-only API를 스텝으로 호출해 판정한 장면(챗봇 탈출).
4. **🤖 AI 재조사 버튼**(approver) — 실시간으로 다시 조사시켜 보기.
5. **🤖 AI 어시스턴트** — 자연어로 질문 → RAG 답변 + 근거 확인.
6. **AI·시스템** — 엔진·모델·Bedrock 사용량·RAG 통계로 "AI가 실제로 돈다"를 관측.
7. **조치** — approver로 승인 → HITL(Step Functions) → **감사로그**에서 불변 기록 확인.
8. **컴플라이언스** — ISMS-P 충족률로 마무리.

---

## 6. 자주 부딪히는 것 (FAQ / 트러블슈팅)

| 증상 | 원인 / 대응 |
|---|---|
| 로그인 화면에서 안 넘어감 | Fresh apply면 Cognito 풀 ID가 바뀜 → **Entra 앱 SAML 식별자**를 새 풀(`urn:amazon:cognito:sp:<pool-id>`)로 갱신해야 함(manual-infra §5). |
| Evidence 판정이 refuted | 오류 아님 — 실 Bedrock이 실제 증거로 조사한 결과. 타깃 결함 토글이 off면 정직하게 refuted. |
| AI 재조사 버튼이 안 보임 | viewer 역할. approver만 가능(Bedrock 비용 액션). |
| finding은 있는데 AI 설명이 비어 있음 | 그 finding이 조사 case에 안 묶였거나 `ai_status`≠done. escalate된 것만 조사됨(비용 통제). |
| /chat 답변에 근거가 없음 | RAG 코퍼스(rag_chunks) 미적재. `/system`에서 청크 수 확인 → 코퍼스 로드 필요. |
| 화면이 순백(빈 화면) | (이 윈도우 머신 한정) SPA 배포 시 `.js` MIME가 text/plain으로 태깅되는 함정 → terraform apply 또는 `aws s3 cp --content-type`으로 배포. |

---

## 7. 기술 스택 (요약)
- **프론트**: Vite + React + TypeScript + Tailwind + TanStack Query + React Flow(그래프) + MSW(목업).
- **백엔드**: `apps/console-backend`(TypeScript, ALB→Lambda) — findings 읽기 API + RAG `/chat` + `/system` 관측 + 조치 트리거.
- **데이터**: RDS PostgreSQL + pgvector(findings·attack_paths·cases·finding_explanations·rag_chunks).
- **인증**: Entra ID(IdP) ─SAML→ Cognito ─OIDC→ SPA(PKCE).
- **AI**: Amazon Bedrock(Claude Haiku — 조사·챗 / Titan v2 — 임베딩).
- **목업↔실데이터 스왑**: `VITE_USE_MOCK` 한 플래그로 전환(화면 코드 무변경). 상세 = [console-app-design.md §15](console-app-design.md).
