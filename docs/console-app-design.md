# 관제 앱 설계도 — 보안 관제 플랫폼 (NOVA 대응)

> **문서 종류:** 관제 앱 설계도 — 우리가 만드는 보안 관제 플랫폼(NOVA 대응)
> **목적:** posture·findings·attack-path를 보여주는 "얼굴"의 화면 구조·백엔드·RBAC·RAG↔UI 매핑을 정의한다. 타깃 앱이 만든 findings를 *어떻게 보여주고 조치하는가*의 구현 기준.
> **관련 문서:** 전체 방향·결정 → [project-draft.md](project-draft.md) · findings를 만들어내는 타깃 앱·골든 시나리오 → [target-app-design.md](target-app-design.md)
> **읽는 순서:** project-draft 8.2·9·10·12~17번을 먼저 본 뒤 이 문서로 화면·백엔드를 잡는다. 타깃 앱이 어떤 결함을 내보내는지는 target 설계도 참조.
>
> 성격: 우리가 만드는 **메인 앱**. 타깃 앱(고객사 워크로드)이 깔린 클라우드 환경의 posture·findings·attack-path를
> 한 화면에서 보여주고, 그 위에 에이전틱 AI(Bedrock)로 설명·우선순위화·조치까지 잇는다. HALO의 NOVA(통합 관제 화면) 대응.
> 핵심 원칙 3가지:
> 1. **타깃 앱의 코드가 아니라 "타깃 앱이 깔린 클라우드 환경"을 본다** — CSPM·CIEM·취약점·KSPM·데이터·attack-path 6기둥.
> 2. **챗봇이 아니라 능동 에이전트** — 사용자가 묻기 전에 finding을 설명·정렬·조사한다. 자연어 질의창은 보조일 뿐 메인이 아니다.
> 3. **타깃 앱과 직접 통신하지 않는다** — findings 저장소(pgvector)만 읽는다(agentless). 상세는 9번.
>
> 본 문서는 메인 설계서([project-draft.md](project-draft.md)) 8.2·9·10·12~17번을 구현 관점으로 상세화한 것이며,
> 타깃 앱 쪽 정답지는 [target-app-design.md](target-app-design.md)를 따른다.

---

## 1. 포지셔닝 — 왜 이 화면인가

타깃 앱과 관제 앱의 역할·대상·인증·변경 권한을 대비한 표다.

| | 타깃 앱 | 관제 앱 |
|---|---|---|
| 역할 | 일부러 취약한 고객사 시스템 (findings **소스**) | 그 환경을 점검·설명·조치하는 **얼굴** |
| 점검 대상 | (점검당하는 줄도 모름) | AWS+Azure 계정의 설정·권한·워크로드·데이터 |
| AI | 없음 | Bedrock 멀티에이전트 + RAG 핵심 |
| 인증 | 없음 | Entra ID→Cognito→ALB SSO |
| 변경 | 없음(읽기 전용 스캔 대상) | 조치 제안 + HITL 승인 → Step Functions |

**시나리오 한 줄:** 고객사(타깃 앱)는 취약하게 운영되고 있고, 우리는 그 계정을 read-only로 스캔해 발견한 위험을
관제 앱에서 보여주고, AI로 설명·우선순위화하며, 승인을 받아 안전하게 고쳐준다.

---

## 2. 화면 구성 (정보 구조)

각 화면의 내용과 연관 유스케이스를 정리한 표다.

| 화면 | 내용 | 연관 유스케이스 |
|---|---|---|
| **로그인** | Entra ID SSO (ALB authenticate-oidc 리다이렉트) | 10번 |
| **대시보드 홈** | AWS+Azure secure score 나란히, 6기둥 요약 카드, **클라우드 경계를 가로지르는 최근 크로스클라우드 attack-path 배너**(멀티클라우드 차별점을 첫 화면에서 강조) | — |
| **Findings 목록** | 6기둥 필터(CSPM/CIEM/취약점/KSPM/데이터/attack-path), 클라우드 필터(AWS/Azure), 상태 필터(open/remediated/suppressed, 기본 open), AI 우선순위 정렬(기본값) | UC2 |
| **Finding 상세** | AI 설명 카드(왜 위험한지+근거 CIS/KEV+조치법), Evidence 탭(능동 수집한 API 호출·결과), 신뢰점수, 상태 이력(open→remediated 타임라인) | UC0, UC1 |
| **Attack-path 그래프** | 노드(리소스)+엣지(관계) 시각화, **AWS 워크로드/Azure 신원 클라우드 경계를 시각적으로 구분(레인/박스)하고 경계를 넘는 크로스클라우드 엣지를 강조**, "공격자가 AWS 워크로드로 들어와 ~를 타고 **Azure Entra ID 신원까지 장악**" 내러티브 텍스트 | UC3 |
| **조치(Remediation)** | 제안 Fix(Terraform/K8s diff), dry-run 결과, 승인/반려 버튼 → Step Functions 진행 상태 | UC4, 17번 HITL |
| **컴플라이언스 리포트** | ISMS-P 미준수 매핑 + 권고, 내보내기(PDF) | UC5 (보너스) |
| **자연어 질의(보조)** | 화면 한 귀퉁이 챗 위젯. RAG 조회 보조용, 메인 아님 | — |
| **감사로그 뷰어** | 모든 AI 판정의 근거·증거·승인 이력 읽기 전용 조회 | 17번 |

### 2.1 빈 상태(empty state) 처리 — 데모 초반 텅 빈 화면 방지

스캔 전·findings 0개 상태에서도 화면이 "고장난 것처럼" 보이지 않도록 각 화면에 명시적 빈 상태를 둔다.

| 화면 | 빈 상태(스캔 전 / findings 0개) | 처리 |
|---|---|---|
| 대시보드 홈 | secure score 미산출, 카드 비어 있음 | "초기 스캔 진행 중…" 안내 + 마지막 스캔 시각 표시(없으면 "아직 스캔 없음") |
| Findings 목록 | 표시할 finding 없음 | "발견된 위험 없음 — 스캔 대기 중이거나 모두 조치됨" + 상태 필터를 remediated로 바꿔보라는 힌트 |
| Finding 상세 | (진입 불가) | 목록이 비면 진입 경로 없음 |
| Attack-path 그래프 | 경로 0건 | "상관된 attack-path 없음 — 단일 finding은 목록에서 확인" 안내, 빈 캔버스 대신 placeholder |
| 조치 화면 | 승인 대기 0건 | "승인 대기 중인 조치 없음" |

> 데모 운영 팁: 합성 finding 주입(project-draft 19번 #4)으로 스캐너를 기다리지 않고 골격을 채운 상태에서 시연 → 빈 상태는 "초기화 직후" 또는 "모두 remediated 된 뒤" 자연스러운 맥락에서만 노출.

### 2.2 크로스클라우드 attack-path 시각화 (멀티클라우드 차별점)

멀티클라우드 가치를 "secure score 나란히"로만 약하게 보여주지 않고, **attack-path 그래프에서 AWS→Azure를 가로지르는 모습**으로 한눈에 드러낸다.

- **클라우드 경계 표시:** 캔버스를 AWS 레인 / Azure 레인 두 영역(박스)으로 나누고, 노드를 소속 클라우드 레인에 배치. 노드 색/아이콘으로 클라우드 구분(AWS/Azure 범례).
- **크로스클라우드 엣지 강조:** 경계를 넘는 엣지(예: `order` 평문 시크릿의 **Azure 자격증명** → **Azure Entra ID 과도권한 App Registration/계정**)는 굵은/점선·강조색으로 그려 "여기서 클라우드를 넘는다"를 시각적으로 못 박음.
- **골든 시나리오 매핑:** target-app-design 3번의 1→2→3→4 경로가 AWS 워크로드 레인(product→order→member)에서 시작해 마지막 엣지에서 Azure 신원 레인(Entra ID 앱/계정)으로 건너가는 형태로 렌더 → 데모 하이라이트.
- 내러티브 텍스트도 "AWS 워크로드에서 시작해 **Azure 신원(Entra)으로 건너가** 디렉터리 전체 통제권 장악"처럼 경계 횡단을 명시. ※ MVP는 이 위험 경로의 **분석·시각화**까지, 실제 횡단 동작 구현은 보너스.

---

## 3. 프론트엔드

- **React SPA**, 빌드 결과물을 **S3 + CloudFront**로 정적 호스팅 (project-draft 13번).
- 그래프 시각화: attack-path 노드/엣지는 D3 또는 Recharts 계열로 충분(별도 그래프 DB 없이 postgres 인접 리스트 렌더).
- 인증 토큰(Cognito 발급)을 가진 상태에서만 API 호출 — 정적 자산 자체는 공개, **API 호출만 인증 필요**.
- 역할(아래 7번 RBAC)에 따라 "조치 승인" 버튼 노출 여부가 갈림.

---

## 4. 백엔드 / API 구조 (★ 타깃 앱과 분리 — 확정) ✅

> project-draft에는 백엔드 컴퓨트가 명시돼 있지 않음. v1에서는 "타깃 앱과 같은 EKS 클러스터의 `console` 네임스페이스"를 제안했으나, **보안상 모순**으로 v2에서 분리 결정.

**확정: 관제 앱 백엔드는 타깃 앱과 같은 클러스터/계정 경계에 두지 않고 분리한다. 구현은 `ALB(authenticate-oidc) → Lambda` (서버리스 API)로 한다.**

### 왜 분리하는가 (v1 제안 폐기 이유)
- 타깃 앱은 **의도적으로 취약**하다 — privileged 파드·과도 IRSA·열린 SG. 관제 백엔드를 같은 EKS 클러스터에 두면 (a) 취약 워크로드와 fault domain(노드·네트워크·RBAC)을 공유해 **공격 경로가 관제까지 닿는다는 모순**이 생기고, (b) "점검하는 자"와 "점검당하는 취약 환경"이 한 클러스터에 섞여 시나리오 설득력이 깨진다.
- 관제 백엔드는 read-only first(17번)의 신뢰 기점이므로, 취약 환경과 **명확한 경계 분리**가 그 자체로 설계 메시지다.

### 선택: Lambda(서버리스) — 별도 클러스터 대신
- **보안 분리:** 타깃 EKS와 완전히 다른 실행 환경·IAM 경계. 공유 fault domain 없음.
- **비용:** 두 번째 EKS 컨트롤플레인($0.10/h)·노드 없이 scale-to-zero → project-draft 22번 "데모만 켜고 destroy" 가드레일과 정합.
- **워크로드 성격:** console-backend는 **주로 읽기**(pgvector 조회) + 가끔 Bedrock/Step Functions 호출 → 서버리스에 잘 맞음.
- **SSO 보존:** ALB는 Lambda 타깃 + `authenticate-oidc` 액션을 함께 지원 → project-draft 10번 SSO 플로우(Entra→Cognito→ALB)를 그대로 유지.

```
[React 빌드] → S3 + CloudFront (정적 자산)
[사용자 API 요청] → ALB(authenticate-oidc, Cognito) → Lambda(console-backend)   ← 타깃 EKS와 별개 환경
                                                              │ (read-only IAM 역할)
                                            ┌─────────────────┼─────────────────┐
                                            ▼                 ▼                 ▼
                                   RDS Aurora PostgreSQL   Bedrock        Step Functions
                                   (pgvector: findings+RAG)  (자연어 질의/   (조치 승인 후 실행,
                                                              재분석 보조)     StartExecution 트리거만)
```

- `console-backend`(Lambda)는 **read-only IAM 역할**을 기본으로 가지며, 조치 실행은 직접 하지 않고 Step Functions `StartExecution`만 호출(분리된 승인 경로, 17번 거버넌스와 일치).
- 공유 에이전틱 엔진(`engine/`)은 별도 Lambda/Step Functions로 동작하며 findings 파이프라인 쪽에서 이미 pgvector에 결과를 적재 — console-backend는 **주로 읽기**, 자연어 질의·재분석 요청 시에만 Bedrock을 능동 호출.
- RDS는 타깃 앱 워크로드가 접근하지 않는 관제 전용 경계에 둔다(타깃은 findings 저장소를 모름, 9번 agentless 원칙).

> 대안(별도 EKS 클러스터)은 분리는 달성하나 비용·운영 부담이 커 데모 범위에서 제외. 추후 관제 백엔드가 상시 운영·확장성을 요구하면 재검토.

---

## 5. Findings 데이터 모델 (pgvector 위 스키마, 제안)

pgvector 위에 둘 주요 테이블과 컬럼·용도를 정리한 표다.

| 테이블 | 주요 컬럼 | 용도 |
|---|---|---|
| `findings` | id, cloud(aws/azure), pillar(cspm/ciem/vuln/kspm/data/attack_path), severity, resource_arn, control_id, status(open/remediated/suppressed), priority_score, attack_path_id | 목록·필터·정렬 |
| `finding_explanations` | finding_id, ai_summary, evidence_json, confidence_score, rag_refs[] | Finding 상세 카드(UC0·UC1) |
| `attack_paths` | id, narrative_text, nodes_json, edges_json, severity | attack-path 화면(UC3) |
| `remediation_requests` | id, finding_id, proposed_fix_diff, status(pending/approved/rejected/applied), approver, step_function_arn | 조치 승인 플로우(UC4) |
| `rag_chunks` (pgvector) | embedding, text, metadata{cloud, service, framework, control_id, severity, isms_p} | RAG 코퍼스(16번) |

> OCSF 정규화 결과를 `findings`에 매핑, 16번 RAG 코퍼스 청킹 규칙("컨트롤/룰 1개=1청크")을 `rag_chunks.metadata`에 그대로 사용.

### 5.1 attack-path 그래프 렌더링 방식 — 확정

**콘솔의 그래프 렌더링은 `attack_paths.nodes_json` / `edges_json`(pgvector 위 커스텀 인접 리스트)을 그대로 그린다. 별도 그래프 DB(Neptune 등)는 쓰지 않는다.**

| 방식 | 평가 |
|---|---|
| **커스텀 postgres 인접 리스트 (채택)** | 코퍼스/노드 규모 작음, findings와 같은 DB에 동거(추가 인프라 0), D3/Recharts로 렌더 충분, 크로스클라우드 노드(AWS+Azure)를 한 스키마로 통합 표현 — 데모에 최적. |
| Security Hub exposure 병행 | AWS 내부 상관엔 강하나 Azure를 못 덮어 **크로스클라우드 경로를 단독으로 못 그림**, 콘솔이 또 변환해야 함. |

> 단, **상류(upstream)에서 attack-path를 무엇으로 상관·계산할지**(엔진 커스텀 상관 vs Security Hub exposure를 입력으로 활용 vs 병행)는 콘솔 렌더링과 별개 문제이며 **project-draft 24번에 열린 항목**으로 남는다. 콘솔은 어느 쪽이 계산하든 `attack_paths` 테이블만 읽어 그린다(소스 독립).

---

## 6. 에이전틱 엔진 연동 — 콘솔이 하는 일 vs 이미 끝난 일

15번 에이전트 5종(Orchestrator→Triage→Hypothesis→Evidence→Reasoning)은 **공유 파이프라인 쪽에서 자동 실행**되고
결과만 pgvector에 적재된다. 관제 앱(콘솔)이 능동적으로 개입하는 지점은 셋뿐이다.

| 콘솔 액션 | 호출 | UI 위치 |
|---|---|---|
| **자연어 질의(보조)** | console-backend → Bedrock(RAG 조회) | 챗 위젯(한 귀퉁이) |
| **재분석 요청** | 사용자가 "다시 분석" 클릭 → Orchestrator 재트리거(선택 기능) | Finding 상세 |
| **조치 승인** | 승인 클릭 → Step Functions `StartExecution`(콘솔은 트리거만, 실행은 분리된 역할) | 조치 화면 |

나머지(UC0 Evidence 능동 수집, UC1 자동 설명, UC2 우선순위, UC3 attack-path 내러티브)는 **표시만** 한다 — 콘솔이 다시 계산하지 않음.

### 6.1 Finding 상태 동기화 루프 (수정 → 소멸) ★

고친 finding이 어떻게 `open → remediated`로 바뀌어 콘솔에서 사라지는지. **상태 전이의 주인은 수집 파이프라인이고 콘솔은 읽기만** 한다(suppress 제외, 아래).

```
[조치 적용]  HITL 승인 → Step Functions → 리소스 변경(예: 버킷 private화, SG 0.0.0.0 제거)
     │
     ▼
[다음 스캔 주기]  스캐너 재스캔(Config/Prowler/Inspector/Trivy/kube-bench/Defender) → 그 위반을 더는 발견 못 함
     │
     ▼
[수집 파이프라인]  재스캔 결과 OCSF 정규화 → 엔진이 기존 finding과 (resource_arn + control_id) 키로 대조
     │
     ▼
[상태 갱신]  해당 키가 이번 스캔에 없음 → findings.status: open → remediated  (DB는 파이프라인이 갱신)
     │
     ▼
[콘솔]  다음 폴링에서 status=remediated 수신 → 기본 필터(open)에서 사라짐
        (이력은 'remediated' 상태 필터로 조회, Finding 상세의 상태 타임라인에 보존)
```

- **매칭 키:** `resource_arn + control_id`. 재스캔에서 같은 키가 다시 잡히면 `remediated → open`으로 되돌림(드리프트 = 재발 탐지) → project-draft 19번 #3(역방향 수정→소멸)·드리프트 검증과 직결.
- **삭제가 아니라 상태 전이:** 사라진 finding을 지우지 않고 `remediated`로 두어 "고쳤다"는 증거·MTTR(KPI) 산정 근거로 남긴다.
- **콘솔이 직접 바꾸는 유일한 상태 = `suppressed`:** approver가 "위험 수용/오탐"으로 수동 보류. open/remediated 전이는 콘솔이 손대지 않음.
- 데모에서는 스캐너 주기를 기다리는 대신, 합성 finding 주입/제거(19번 #4)나 수동 재스캔 트리거로 이 루프를 빠르게 시연.

### 6.2 갱신 주기 / 실시간성 — 콘솔이 pgvector를 언제 다시 읽나

> 스캐너(Config/Prowler/Inspector 등)는 본래 실시간이 아니라 **주기·이벤트성**이다. 콘솔도 그에 맞춰 과한 실시간성을 추구하지 않는다.

**확정(데모 기준):**
- **Findings 목록·대시보드:** 프론트가 **30~60초 주기 폴링** + **수동 새로고침 버튼**. 마지막 갱신 시각을 화면에 표시.
- **Finding 상세·attack-path:** 진입/펼침 시 on-demand 조회(상시 폴링 아님).
- **조치 진행 상태:** 승인 후 Step Functions 실행 중에는 해당 화면만 짧은 주기(5~10초) 폴링으로 진행 표시.
- **이벤트 기반 push(WebSocket/SSE)는 데모 범위 밖** — 폴링으로 충분하고 단순. 상시 운영 시 확장 항목.

---

## 7. SSO 통합 + 역할(RBAC) — 콘솔 관점 🔒

```
사용자 → 관제 앱 접속 → ALB(authenticate-oidc) 미인증 시 Cognito로 리다이렉트
       → Cognito가 Entra ID로 페더레이션(SAML, Entra=IdP)
       → 로그인 성공 → Cognito 토큰(그룹 클레임 포함) 발급 → 관제 앱 진입
```

- Entra ID 그룹 클레임 → Cognito 토큰에 매핑 → 콘솔에서 **2개 역할**로 단순화해 사용(제안):
  - **분석가(viewer):** 모든 화면 조회만, 조치 제안 확인 가능, 승인 불가.
  - **보안관리자(approver):** 조치 승인/반려 가능 — 17번 "변경은 분리된 승인 경로로만"을 역할 분리로 구현.
- 무료 가능 근거·구현 방식은 project-draft 10번을 그대로 따름(Week 1 우선 검증 대상).
- **데모 시연:** Entra ID에 그룹 2개(`cnapp-viewer`, `cnapp-approver`)와 테스트 계정 2개를 만들고 각 그룹에 배정 → 그룹 클레임이 Cognito 토큰에 실려 콘솔에서 분석가/보안관리자로 갈림. 시연은 viewer로 로그인(승인 버튼 비활성) → approver로 재로그인(승인 버튼 활성·조치 승인)으로 역할 분리를 보여줌.

---

## 8. RAG/Bedrock 유스케이스 ↔ UI 매핑

각 유스케이스(UC0~UC5)가 어느 화면에 매핑되는지 정리한 표다.

| UC | 내용 | 화면 |
|---|---|---|
| UC0 | Evidence 능동 수집(read-only API 호출로 검증·보강) | Finding 상세 "Evidence" 탭 |
| UC1 | 자동 생성 리포트(왜 위험한지+근거+조치법) | Finding 상세 메인 카드 |
| UC2 | 우선순위 자동 정렬 | Findings 목록 기본 정렬 |
| UC3 | attack-path 내러티브 | attack-path 화면 스토리 텍스트 |
| UC4 | 조치 코드 생성(Fix) | 조치 화면 diff 미리보기 + 승인 버튼 |
| UC5 | 컴플라이언스 리포트(ISMS-P) | 컴플라이언스 리포트 화면(보너스) |

---

## 9. 연결 구조 재확인 (★ agentless) 🔒

타깃 앱과 관제 앱은 **직접 통신하지 않는다.** 관제 앱은 findings 저장소(pgvector)만 읽고, 타깃 앱이 무엇인지 모른다.

```
[타깃 앱] → AWS/Azure 계정에 배포만 됨
              │ read-only 스캔(Config·Prowler·Inspector·Trivy·kube-bench·Macie·Defender)
              ▼
        [ findings ] → EventBridge→SQS→Lambda → OCSF 정규화 → 공유 에이전틱 엔진 → pgvector
                                                                                    │
                                                                  console-backend가 읽음
                                                                                    ▼
                                                                              [ 관제 앱 ]
```

API가 있는 곳은 ① 스캐너↔클라우드 API(읽기) ② console-backend↔pgvector/Bedrock/Step Functions ③ 콘솔 프론트↔console-backend 뿐.
타깃 앱과의 직접 API는 없음(target-app-design.md 5번과 동일 원칙).

---

## 10. 거버넌스 — 콘솔 UI에서 보이는 부분 🔒

- **감사로그 뷰어:** 원본 불변 로그는 S3 Object Lock에 저장(17번). 조회 편의를 위해 요약본을 `remediation_requests`/`finding_explanations`에도 같이 적재해 콘솔에서 빠르게 검색 — 단, 콘솔은 **요약 인덱스만 보여주고 원본 신뢰점은 S3**.
- **승인 대기열(Pending Approval Queue):** 조치 화면 상단에 고정. dry-run 결과·영향 리소스·되돌리기(rollback) 경로를 승인 전 필수로 노출.
- **읽기 전용 기본값:** 콘솔 자체 IAM(Lambda 실행 역할)도 read-only가 기본 — 승인된 조치만 Step Functions를 통해 격상된 역할로 실행(최소권한, 17번).

---

## 11. 기술 스택 요약

영역별 기술 선택과 근거 절을 한데 모은 표다.

| 영역 | 선택 | 비고 |
|---|---|---|
| 프론트엔드 | React, S3+CloudFront | 정적 호스팅 |
| 인증 | Cognito(SP/허브) ← Entra ID(IdP, SAML) ← ALB authenticate-oidc | 10번 |
| 백엔드 | **Lambda(서버리스) ← ALB(authenticate-oidc)** — 타깃 EKS와 분리 | 4번(v2 확정) |
| 데이터/RAG | RDS Aurora PostgreSQL + pgvector | D9, 16번 |
| AI | Bedrock(에이전틱 엔진 + 자연어 질의 보조) | 9번(project-draft) |
| 조치 실행 | Step Functions + S3 Object Lock(감사) | 17번 |
| 권한 | read-only IAM 기본(Lambda 실행 역할), 조치만 격상 역할 분리 | D5, 17번 |

---

## 12. infra/console 매핑 (Terraform 골격) 🏗️

> v2: 백엔드를 타깃 EKS와 분리(4번 확정)함에 따라 EKS 네임스페이스/Ingress 대신 **Lambda + ALB** 골격으로 갱신.

- Cognito User Pool + Identity Pool(SAML IdP = Entra ID 등록 포함)
- S3(정적 자산) + CloudFront 배포
- **ALB + 리스너 규칙(`authenticate-oidc` 액션) → Lambda 타깃 그룹**(타깃 EKS와 별개 환경)
- **console-backend Lambda 함수**(read-only 실행 역할) + 로그 그룹
- RDS Aurora PostgreSQL(pgvector extension 활성화) — `engine/`과 공유, 관제 전용 경계(타깃 워크로드 비접근)
- Step Functions 상태 머신(조치 카탈로그 1차 범위는 project-draft 24번 미확정 항목, 결정 시 본 문서 갱신)
- IAM: 콘솔용 read-only 롤 / 조치 실행용 격상 롤 분리(별도 정책)

---

## 13. 구현 순서 (project-draft 21번 로드맵에 맞춤, 콘솔 관점만 발췌) 🗓️

> v2: attack-path 그래프는 데모 하이라이트이므로 Day 10 → **Day 7~8로 상향**(project-draft 21번 Week2 Day6–7 "attack-path 1차"와도 정합). Azure 통합과 같은 구간에 묶어 크로스클라우드 모습을 일찍 확보.

Day 단위 콘솔 작업과 연계 절을 정리한 표다.

| Day | 콘솔 작업 |
|---|---|
| 1–2 | SSO(Entra→Cognito→ALB) 우선 검증, 정적 호스팅 골격, **빈 상태 처리(2.1)** |
| 3–4 | findings 읽기 API + 목록/상세 화면(초기엔 목업 데이터로 골격 먼저), **폴링/수동 새로고침(6.2)** |
| 5 | UC1(자동 설명) 실제 연동 — Finding 상세 카드 살아남 |
| 6 | UC2(우선순위 정렬) + 대시보드 v1(AWS secure score) |
| **7–8** | **attack-path 그래프(UC3) 1차 + 크로스클라우드 시각화(2.2)** + Azure secure score 나란히(멀티클라우드 통합 뷰) |
| 9 | 조치 승인(HITL) UI + Step Functions 연동, RBAC 2역할 적용, **상태 동기화 루프(6.1) 시연** |
| 10 | attack-path 내러티브·시각 정교화 + 감사로그 뷰어 + 데모 마감 |

---

## 14. 미확정 / 제안 사항 (project-draft 24번과 연동, 결정 시 갱신) ❓

**v2에서 확정(미확정에서 제거):** 백엔드 컴퓨트 = Lambda·타깃 EKS와 분리(4번) / attack-path 콘솔 렌더링 = 커스텀 postgres 인접 리스트(5.1) / 갱신 주기 = 30~60초 폴링+수동 새로고침(6.2) / RBAC = 2역할·Entra 그룹 매핑(7번).

**여전히 열린 항목:**
- [ ] **attack-path 상류 상관 계산 소스** — Security Hub exposure vs 엔진 커스텀 상관 vs 병행. **project-draft 24번과 동일 항목.** (콘솔 렌더링 방식은 5.1에서 커스텀 postgres로 확정; 무엇이 경로를 *계산*하는지가 열림.)
- [ ] **자동 조치 카탈로그 1차 범위** — 어떤 finding까지 자동 Fix 제안을 허용할지. **project-draft 24번과 동일 항목**, 콘솔 UI 노출 범위와 직결.
- [ ] 컴플라이언스 리포트(UC5) PDF 내보내기 구현 방식 — 보너스 우선순위라 후순위.

---

*관제 앱 설계도 — 메인 설계서(project-draft v5)의 8.2·9·10·12~17번을 구현용으로 상세화.*

*v2 변경 요약: Finding 상태 동기화 루프(6.1)·갱신 주기(6.2 폴링) 추가, 백엔드를 타깃 EKS와 분리해 Lambda로 확정(4·11·12번), attack-path 콘솔 렌더링 커스텀 postgres 확정(5.1)·구현 순서 Day 7~8로 상향(13번), 빈 상태(2.1)·크로스클라우드 attack-path 시각화(2.2)·RBAC 데모 시연(7번) 보강, 14번 미확정을 project-draft 24번과 동기화.*

*v2.1 변경 요약: **Azure 역할을 데이터→신원(Entra ID) 중심으로 전환에 맞춰 attack-path 화면·시각화 갱신.** 크로스클라우드 엣지를 "공개 S3→Azure 공개 Blob"에서 **"order 평문 시크릿의 Azure 자격증명→Entra ID 과도권한 앱/계정 장악"**으로 교체, 레인을 AWS 워크로드 / Azure 신원으로 명시, 내러티브를 "디렉터리 전체 통제권 장악"으로 갱신. MVP는 분석·시각화 수준이고 실제 횡단 동작은 보너스임을 명시. 문서 식별 헤더 추가.*
