# 관제 앱 설계도 — 보안 관제 플랫폼 (NOVA 대응)

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

| 화면 | 내용 | 연관 유스케이스 |
|---|---|---|
| **로그인** | Entra ID SSO (ALB authenticate-oidc 리다이렉트) | 10번 |
| **대시보드 홈** | AWS+Azure secure score 나란히, 6기둥 요약 카드, 최근 attack-path 알림 | — |
| **Findings 목록** | 6기둥 필터(CSPM/CIEM/취약점/KSPM/데이터/attack-path), 클라우드 필터(AWS/Azure), AI 우선순위 정렬(기본값) | UC2 |
| **Finding 상세** | AI 설명 카드(왜 위험한지+근거 CIS/KEV+조치법), Evidence 탭(능동 수집한 API 호출·결과), 신뢰점수 | UC0, UC1 |
| **Attack-path 그래프** | 노드(리소스)+엣지(관계) 시각화, "공격자가 ~로 들어와 ~를 탈취" 내러티브 텍스트 | UC3 |
| **조치(Remediation)** | 제안 Fix(Terraform/K8s diff), dry-run 결과, 승인/반려 버튼 → Step Functions 진행 상태 | UC4, 17번 HITL |
| **컴플라이언스 리포트** | ISMS-P 미준수 매핑 + 권고, 내보내기(PDF) | UC5 (보너스) |
| **자연어 질의(보조)** | 화면 한 귀퉁이 챗 위젯. RAG 조회 보조용, 메인 아님 | — |
| **감사로그 뷰어** | 모든 AI 판정의 근거·증거·승인 이력 읽기 전용 조회 | 17번 |

---

## 3. 프론트엔드

- **React SPA**, 빌드 결과물을 **S3 + CloudFront**로 정적 호스팅 (project-draft 13번).
- 그래프 시각화: attack-path 노드/엣지는 D3 또는 Recharts 계열로 충분(별도 그래프 DB 없이 postgres 인접 리스트 렌더).
- 인증 토큰(Cognito 발급)을 가진 상태에서만 API 호출 — 정적 자산 자체는 공개, **API 호출만 인증 필요**.
- 역할(아래 7번 RBAC)에 따라 "조치 승인" 버튼 노출 여부가 갈림.

---

## 4. 백엔드 / API 구조 (제안)

> project-draft에는 백엔드 컴퓨트가 명시돼 있지 않음(24번 미확정과 연결). 아래는 **제안**이며 확정 시 본 문서·CLAUDE.md를 갱신한다.

**제안: 관제 앱 백엔드도 타깃 앱과 같은 EKS 클러스터에, 별도 네임스페이스(`console`)로 배포.**

이유:
- D6(EKS+ArgoCD GitOps가 핵심 축)을 그대로 재사용 — 별도 Fargate/Lambda 환경을 새로 안 만들어도 됨.
- ALB Ingress Controller가 `alb.ingress.kubernetes.io/auth-type: oidc` 어노테이션으로 **authenticate-oidc를 그대로 지원** → project-draft 10번 SSO 플로우와 정확히 맞물림.
- 비용·운영 추가 부담 없음(무료 티어 가드레일과 충돌 없음).

```
[React 빌드] → S3 + CloudFront (정적 자산)
[사용자 API 요청] → ALB(authenticate-oidc, Cognito) → EKS Ingress → console-backend Pod(EKS, IRSA)
                                                              │
                                            ┌─────────────────┼─────────────────┐
                                            ▼                 ▼                 ▼
                                   RDS Aurora PostgreSQL   Bedrock        Step Functions
                                   (pgvector: findings+RAG)  (자연어 질의/   (조치 승인 후
                                                              재분석 보조)     실행, IRSA로 트리거만)
```

- `console-backend`는 **read-only IRSA 역할**을 기본으로 가지며, 조치 실행은 직접 하지 않고 Step Functions `StartExecution`만 호출(분리된 승인 경로, 17번 거버넌스와 일치).
- 공유 에이전틱 엔진(`engine/`)은 별도 Lambda/Step Functions로 동작하며 findings 파이프라인 쪽에서 이미 pgvector에 결과를 적재 — console-backend는 **주로 읽기**, 자연어 질의·재분석 요청 시에만 Bedrock을 능동 호출.

---

## 5. Findings 데이터 모델 (pgvector 위 스키마, 제안)

| 테이블 | 주요 컬럼 | 용도 |
|---|---|---|
| `findings` | id, cloud(aws/azure), pillar(cspm/ciem/vuln/kspm/data/attack_path), severity, resource_arn, control_id, status(open/remediated/suppressed), priority_score, attack_path_id | 목록·필터·정렬 |
| `finding_explanations` | finding_id, ai_summary, evidence_json, confidence_score, rag_refs[] | Finding 상세 카드(UC0·UC1) |
| `attack_paths` | id, narrative_text, nodes_json, edges_json, severity | attack-path 화면(UC3) |
| `remediation_requests` | id, finding_id, proposed_fix_diff, status(pending/approved/rejected/applied), approver, step_function_arn | 조치 승인 플로우(UC4) |
| `rag_chunks` (pgvector) | embedding, text, metadata{cloud, service, framework, control_id, severity, isms_p} | RAG 코퍼스(16번) |

> OCSF 정규화 결과를 `findings`에 매핑, 16번 RAG 코퍼스 청킹 규칙("컨트롤/룰 1개=1청크")을 `rag_chunks.metadata`에 그대로 사용.

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

---

## 7. SSO 통합 + 역할(RBAC) — 콘솔 관점

```
사용자 → 관제 앱 접속 → ALB(authenticate-oidc) 미인증 시 Cognito로 리다이렉트
       → Cognito가 Entra ID로 페더레이션(SAML, Entra=IdP)
       → 로그인 성공 → Cognito 토큰(그룹 클레임 포함) 발급 → 관제 앱 진입
```

- Entra ID 그룹 클레임 → Cognito 토큰에 매핑 → 콘솔에서 **2개 역할**로 단순화해 사용(제안):
  - **분석가(viewer):** 모든 화면 조회만, 조치 제안 확인 가능, 승인 불가.
  - **보안관리자(approver):** 조치 승인/반려 가능 — 17번 "변경은 분리된 승인 경로로만"을 역할 분리로 구현.
- 무료 가능 근거·구현 방식은 project-draft 10번을 그대로 따름(Week 1 우선 검증 대상).

---

## 8. RAG/Bedrock 유스케이스 ↔ UI 매핑

| UC | 내용 | 화면 |
|---|---|---|
| UC0 | Evidence 능동 수집(read-only API 호출로 검증·보강) | Finding 상세 "Evidence" 탭 |
| UC1 | 자동 생성 리포트(왜 위험한지+근거+조치법) | Finding 상세 메인 카드 |
| UC2 | 우선순위 자동 정렬 | Findings 목록 기본 정렬 |
| UC3 | attack-path 내러티브 | attack-path 화면 스토리 텍스트 |
| UC4 | 조치 코드 생성(Fix) | 조치 화면 diff 미리보기 + 승인 버튼 |
| UC5 | 컴플라이언스 리포트(ISMS-P) | 컴플라이언스 리포트 화면(보너스) |

---

## 9. 연결 구조 재확인 (★ agentless)

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

## 10. 거버넌스 — 콘솔 UI에서 보이는 부분

- **감사로그 뷰어:** 원본 불변 로그는 S3 Object Lock에 저장(17번). 조회 편의를 위해 요약본을 `remediation_requests`/`finding_explanations`에도 같이 적재해 콘솔에서 빠르게 검색 — 단, 콘솔은 **요약 인덱스만 보여주고 원본 신뢰점은 S3**.
- **승인 대기열(Pending Approval Queue):** 조치 화면 상단에 고정. dry-run 결과·영향 리소스·되돌리기(rollback) 경로를 승인 전 필수로 노출.
- **읽기 전용 기본값:** 콘솔 자체 IAM(IRSA)도 read-only가 기본 — 승인된 조치만 Step Functions를 통해 격상된 역할로 실행(최소권한, 17번).

---

## 11. 기술 스택 요약

| 영역 | 선택 | 비고 |
|---|---|---|
| 프론트엔드 | React, S3+CloudFront | 정적 호스팅 |
| 인증 | Cognito(SP/허브) ← Entra ID(IdP, SAML) ← ALB authenticate-oidc | 10번 |
| 백엔드 | 컨테이너(EKS `console` 네임스페이스), ALB Ingress(oidc) | 4번 제안 |
| 데이터/RAG | RDS Aurora PostgreSQL + pgvector | D9, 16번 |
| AI | Bedrock(에이전틱 엔진 + 자연어 질의 보조) | 9번(project-draft) |
| 조치 실행 | Step Functions + S3 Object Lock(감사) | 17번 |
| 권한 | IRSA(read-only 기본, 조치만 격상 역할 분리) | D5, 17번 |

---

## 12. infra/console 매핑 (Terraform 골격, 제안)

- Cognito User Pool + Identity Pool(SAML IdP = Entra ID 등록 포함)
- S3(정적 자산) + CloudFront 배포
- ALB 리스너 규칙(authenticate-oidc 액션) + Ingress 어노테이션 연동
- RDS Aurora PostgreSQL(pgvector extension 활성화) — `engine/`과 공유
- Step Functions 상태 머신(조치 카탈로그 1차 범위는 24번 미확정 항목, 결정 시 본 문서 13번 갱신)
- IAM: 콘솔용 read-only 롤 / 조치 실행용 격상 롤 분리(별도 정책)

---

## 13. 구현 순서 (project-draft 21번 로드맵에 맞춤, 콘솔 관점만 발췌)

| Day | 콘솔 작업 |
|---|---|
| 1–2 | SSO(Entra→Cognito→ALB) 우선 검증, 정적 호스팅 골격 |
| 3–4 | findings 읽기 API + 목록/상세 화면(초기엔 목업 데이터로 골격 먼저) |
| 5 | UC1(자동 설명) 실제 연동 — Finding 상세 카드 살아남 |
| 6–7 | UC2(우선순위 정렬) + 대시보드 v1(AWS secure score) |
| 8 | Azure secure score 나란히 표시(멀티클라우드 통합 뷰) |
| 9 | 조치 승인(HITL) UI + Step Functions 연동, RBAC 2역할 적용 |
| 10 | attack-path 그래프(UC3) + 데모 마감, 감사로그 뷰어 |

---

## 14. 미확정 / 제안 사항 (project-draft 24번과 연동, 결정 시 갱신)

- [ ] 콘솔 백엔드 컴퓨트 확정 — 본 문서는 **EKS 컨테이너**를 제안(4번). Lambda 대안과 비교 후 확정.
- [ ] attack-path 그래프 구현 방식 — 커스텀 postgres 인접 리스트(본 문서 5번 제안) vs Security Hub exposure 병행.
- [ ] RBAC 역할 세부(2역할 단순화 제안, 7번) — Entra 그룹-Cognito 클레임 매핑 규칙 확정 필요.
- [ ] 자동 조치 카탈로그 1차 범위(어떤 finding까지 자동 Fix 제안 허용할지) — project-draft 24번과 동일 항목, 콘솔 UI 노출 범위와 직결.
- [ ] 컴플라이언스 리포트(UC5) PDF 내보내기 구현 방식 — 보너스 우선순위라 후순위.

---

*관제 앱 설계도 — 메인 설계서(project-draft v5)의 8.2·9·10·12~17번을 구현용으로 상세화. 화면 구조·백엔드 제안·RBAC·RAG 매핑 추가. 백엔드 컴퓨트·attack-path 구현 방식은 제안 단계이며 확정 시 본 문서 갱신.*
