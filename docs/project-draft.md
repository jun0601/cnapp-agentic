# Multi-Cloud CNAPP with Agentic AI — 프로젝트 설계서 (v5)

> **문서 종류:** 전체 설계서(SSOT) — 프로젝트 방향·결정·아키텍처 총괄
> **목적:** 이 프로젝트를 *무엇을·왜·어떻게* 만드는지의 단일 진실 공급원. 방향·범위·핵심 결정(D1~D19)·아키텍처·로드맵·미확정 항목을 총괄한다.
> **관련 문서:** 타깃 앱 상세 → [target-app-design.md](target-app-design.md) · 관제 앱 상세 → [console-app-design.md](console-app-design.md) · 수동 관리 리소스 현황 → [manual-infra.md](manual-infra.md) · 협업 규칙 → [CLAUDE.md](../CLAUDE.md)
> **읽는 순서:** 처음 합류한 사람은 이 문서를 먼저 통독한 뒤 타깃/관제 상세로 내려간다. 강사·리뷰어는 1·5·6·11번만 봐도 방향이 잡힌다.
>
> 상태: 방향·범위·분담·앱·멀티클라우드 확정 / 구현 진입 직전
> 성격: 2인 협업 개인 프로젝트(작업 분담, 각자 전체 이해) · 클라우드 보안 엔지니어 포트폴리오
> 한 줄: **AWS는 워크로드의 주인, Azure는 신원의 주인(Entra ID)** — 분산된 멀티클라우드 환경을 하나의 에이전틱 CNAPP으로 점검·통합·자동 개선.

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
- 기업은 클라우드별 강점에 따라 리소스를 **분산**한다: 컨테이너·클라우드 네이티브 워크로드는 AWS, 신원·협업(Microsoft 365 → Entra ID)은 Azure. **데이터 중복 저장은 명분이 약해, Azure는 "데이터 보관처"가 아니라 "신원의 주인"으로 명확히 잡는다.**
- 보안 상태가 **여러 콘솔에 흩어져** 전체 위험 경로가 안 보인다 → 단일 뷰 통합 + 크로스클라우드 attack-path 추적이 핵심 가치.

### 2.3 시장 정렬
- 국내 주요 MSP의 핵심 사업과 직접 매핑: 멀티클라우드 CSPM·CNAPP, AI 네이티브 보안, attack-path 분석, 컴플라이언스(ISMS-P/CSAP).

---

## 3. 방향: CSPM → CNAPP 심화 (SOC 아님)

CSPM을 **넓히지 않고 깊게** 심화하되, **SOC(실시간 위협탐지/대응)가 아니라 workload(코드 방향)로** 깊이를 더한다.

- **SOC 제외 이유:** (a) 진짜 공격 데이터 확보가 어렵고 (b) 자율 대응의 안전성 리스크가 크며 (c) 초점이 흐려진다. → **확장 방향(섹션 18)으로만, 끼울 자리는 비워둠.**
- **workload 심화 이유:** CWPP·KSPM·취약점·IaC 보안은 실제 리소스를 스캔하면 데이터가 바로 나오고, EKS·IaC·CI/CD 역량에 정통으로 꽂힌다.

---

## 4. 작업 분담 (균형안 — 효율용 트랙)

> **원칙:** 다른 환경에서 병렬 작업하기 위해 일을 나누되, **둘 다 상대 영역까지 완전히 이해**한다. 분담은 효율 수단이지 분리 소유가 아니다. 아래는 "각자 한 덩어리씩"이 아니라 **각 영역을 반반 갈라 양쪽이 핵심을 다 만지게** 한 균형안이다.

> ⚠️ **이 분담은 진행하며 계속 조정되는 살아있는 문서다.** 둘이 옆에서 상시 협의 중이며, 변경 시 이 표와 [CLAUDE.md](../CLAUDE.md) 5번을 **함께** 갱신한다.

### 4.1 영역별 분담 (한 표)

| 영역 | 준형 | 진우 | 상태 |
|---|---|---|---|
| **앱** | **타깃 앱(결함 심기) + 관제 앱(대시보드·시각화)** | — (앱 2개 모두 준형 전담) | 확정 |
| **토대** | CI/CD · Shift-Left · **공유인프라 주도** | 모니터링 · 관제 · 추적(Grafana · CloudTrail) | 확정 |
| **스캐너-CSPM** | CSPM(Config · Prowler · Security Hub · **Macie(AWS S3 전용)**) | 워크로드(Inspector · Trivy · kube-bench · **Defender(Azure 리소스)**) | 확정 |
| **스캐너-CIEM** | IAM Access Analyzer(AWS — 외부접근·과도권한 정책 분석) | Entra ID(Azure — **Prowler entra_id_\* 체크**: 과도권한 앱·위험한 consent·권한상승) | 확정 |
| **수집·정규화** | 수집부(EventBridge→SQS) | 정규화부(Lambda→OCSF) | 확정 |
| **엔진(Bedrock)** | **Evidence(tool use)** · Triage | Hypothesis · **Reasoning** · Orchestrator | 확정 |
| **RAG** | 코퍼스 · 임베딩 · pgvector 적재 | 검색 · LLM 답변 생성 | 확정 |
| **attack-path** | 그래프 데이터 모델 | 상관 로직 · 내러티브 | 확정 |

> 전 영역 **확정(2026-06-30, 진우 검증 완료 — 추가 피드백 없음)**. 단 4.1 머리말대로 진행하며 조정될 수 있는 살아있는 분담이며, 바뀌면 이 표와 CLAUDE.md §5를 함께 갱신.
> CIEM은 독립 행으로 분리: AWS는 준형(IAM Access Analyzer — CSPM 인프라 작업과 연결), Azure Entra는 진우(Prowler entra_id_* 체크 — Azure/Defender 작업과 연결).

### 4.3 의존성 순서 (병목 주의 — 데이터 흐름 방향이라 앞 단계가 있어야 뒤가 된다)

```
0. 공유인프라        (준형·최우선 — 없으면 둘 다 멈춤)
1. 앱배포(준형)       ∥  모니터링 골격(진우)
2. 스캐너 준형=CSPM   ∥  진우=워크로드
3. 수집(준형)         →  정규화(진우)             ← 순차(앞이 있어야 뒤)
4. RAG토대 준형=적재  ∥  진우=검색연동
5. 엔진 준형=Evidence ∥  진우=Reasoning
6. 출력 준형=CI/CD·SSO ∥ 진우=관제앱·시각화
7. 골든 시나리오 데모  (둘이 합류)
```

`∥` = 병렬 가능, `→` = 순차(앞 단계 산출물 필요). **0번 공유인프라는 준형이 최우선으로 깐다** — 안 되면 양쪽 모두 블록.

### 4.4 미리 합의할 공통 계약 (이것만 정하면 나머지는 병렬 가능) — 초안 확정

> **이 절이 프로젝트 공통 계약의 단일 거처다.** 준형·진우·관제앱·엔진이 전부 여기 형식대로 읽고 쓴다. 아래는 설계 단계 초안이며, **코딩 시작 시 그대로 `contracts/*.json`(실제 스키마 파일) + `contracts/mock-findings.json`(목업 데이터)으로 졸업**한다 — 코드가 그 파일을 직접 import하므로 산문↔코드 drift가 없다. 별도 schema 문서(.md)는 만들지 않는다.
>
> **계약 우선(contract-first) 전략:** 아래 ①을 확정한 즉시, 그 형식대로 가짜 finding 30~50건(골든 시나리오 포함)을 `contracts/mock-findings.json`으로 만들어 커밋한다. 진우는 실제 스캐너를 기다리지 않고 이 목업으로 콘솔·엔진을 끝까지 만들고, 준형은 같은 계약으로 스캐너·수집을 만든다. 마지막에 목업→실데이터로 교체 → **직렬 의존 사슬(4.3)을 두 병렬 트랙으로 분리.**

#### 계약 ① OCSF-lite finding 스키마 (수집↔정규화↔엔진↔콘솔 공통)

> 풀 OCSF는 2주에 비현실적 → 핵심 필드만 OCSF 네이밍을 차용한 **OCSF-lite**로 시작, 여유되면 필드 확장. **식별자는 클라우드 불문 `resource_id`로 일반화**(Azure Entra는 ARN이 없으므로) → 크로스클라우드 finding을 한 스키마로 묶고 상태 동기화·dedup이 성립한다.

```json
{
  "finding_id": "uuid",
  "cloud": "aws|azure",
  "resource_id": "aws:s3_bucket:member-pii-prod",      // {cloud}:{type}:{native_id} — ARN 대체
  "resource_type": "s3_bucket|app_registration|iam_role|eks_pod|security_group|...",
  "pillar": "cspm|ciem|vuln|kspm|data|attack_path",
  "control_id": "INTERNAL-S3-PUBLIC-001",              // 소스 무관 내부 통일 택소노미
  "title": "S3 bucket allows public access",
  "severity_id": 1,                                     // 1=Critical ~ 5=Info (내부 컨벤션·낮을수록 심각. ※실제 OCSF는 반대(1=Info,5=Crit) → 정규화 시 매핑 주의)
  "status": "open|remediated|suppressed",
  "sources": ["securityhub:S3.8", "config:s3-bucket-public-read-prohibited", "prowler:..."],
  "dedup_key": "aws:s3_bucket:member-pii-prod|INTERNAL-S3-PUBLIC-001",  // resource_id|control_id
  "priority_score": null,                               // 엔진이 채움
  "attack_path_id": null,
  "ai_status": "pending|done|failed",                   // AI 레이어를 finding 레이어와 분리(엔진 실패해도 대시보드는 산다)
  "first_seen": "ts", "last_seen": "ts",                // 신선도
  "raw_ref": "s3://.../raw/...json"
}
```

> **dedup:** `dedup_key` 충돌 시(예: Prowler·Config가 같은 공개 S3를 둘 다 잡음) 머지하고 `sources[]`에 출처 누적 — 중복 카운트 방지. **상태 매칭 키도 `dedup_key`**(기존 `resource_arn + control_id`를 대체).

#### 계약 ② 엔진 입출력 형식 (Evidence→Reasoning) — 프로젝트의 심장

```json
// 입력: Triage → Hypothesis/Evidence
{ "finding": { /* OCSF-lite */ }, "hypotheses": ["이 IRSA 권한이 member S3에 닿을 수 있음", "..."] }

// Evidence 출력: Reasoning이 받는 것
{
  "finding_id": "uuid",
  "evidence": [
    { "tool": "s3:GetBucketPolicy", "resource_id": "aws:s3_bucket:member-pii-prod",
      "result_summary": "Principal:* 허용 확인", "raw": { }, "ts": "..." }
  ],
  "tool_calls_count": 3,
  "confidence_score": 0.0,
  "verdict": "confirmed|refuted|inconclusive"
}
```

#### 계약 ③ attack-path 그래프 JSON (상관로직↔콘솔 렌더↔Reasoning 내러티브 공통)

> 세 번째 공통 계약(기존엔 2개로 셌으나 attack-path 그래프도 공유 계약). `cross_cloud:true` 엣지가 콘솔의 경계 횡단 강조 렌더 트리거, 노드 `cloud`가 AWS/Azure 레인 배치 결정.

```json
{
  "attack_path_id": "uuid", "severity_id": 1,
  "nodes": [
    { "id": "n1", "cloud": "aws",   "resource_id": "aws:eks_pod:product",         "label": "product 취약 이미지(KEV)",      "pillar": "vuln" },
    { "id": "n4", "cloud": "azure", "resource_id": "azure:app_registration:...",  "label": "과도권한 App Registration",   "pillar": "ciem" }
  ],
  "edges": [
    { "from": "n2", "to": "n4", "type": "credential_theft", "cross_cloud": true,
      "label": "order 평문 시크릿의 Azure 자격증명으로 횡단" }
  ],
  "narrative_text": "공격자가 product로 들어와 ... Azure Entra 신원까지 장악(디렉터리 전체 통제권)"
}
```

#### 계약 ④ Evidence 툴 allowlist (read-only 전용) — LLM에 줄 도구 = 능력 정의

> Evidence가 "스스로 호출"하는 API의 화이트리스트. **read-only만**(거버넌스 17번 정합), 변경 API 절대 미포함. 단일 read-only IAM 역할 + Azure read-only Graph 앱 1개로 스코프.

```
AWS:   s3:GetBucketPolicy, s3:GetBucketAcl, s3:GetPublicAccessBlock,
       iam:GetRolePolicy, iam:ListAttachedRolePolicies, iam:SimulatePrincipalPolicy,
       macie2:GetFindings, ec2:DescribeSecurityGroups, accessanalyzer:ListFindings
Azure: (MS Graph read-only) Application.Read.All, Directory.Read.All, RoleManagement.Read.Directory
```

#### 계약 ⑤ 수집 봉투 (ingest envelope) — 수집부↔정규화부 이음새

> 반반 분담으로 드러난 이음새: 준형 수집부가 SQS에 싣는 형식 ↔ 진우 정규화부 Lambda가 읽는 형식. **입구가 둘**(AWS 스캐너 EventBridge 이벤트 + Prowler가 S3에 떨군 OCSF 객체의 S3 이벤트)이라 봉투가 양쪽을 다 덮어야 한다. OCSF-lite(계약①)는 정규화 *후* 형식, 이 봉투는 정규화 *전* 원본 포인터.

```json
{
  "envelope_id": "uuid",
  "source": "securityhub|config|inspector|prowler-aws|prowler-azure|trivy|kube-bench|macie|synthetic",
  "source_format": "asff|ocsf|prowler-json|trivy-json|custom",
  "cloud_hint": "aws|azure",
  "scan_batch_id": "uuid",          // 한 스캔 실행 묶음 — remediated/신선도 판정의 기준(이 배치에 없으면 remediated)
  "ingested_at": "ts",
  "raw_location": "s3://raw-findings/.../obj.json",   // 큰 원본은 S3 포인터
  "raw_inline": null                 // 작으면 인라인(택1)
}
```

> 정규화부는 이 봉투 하나만 보면 됨 — EventBridge발인지 Prowler-S3발인지 몰라도 됨(입구 배관을 수집부가 흡수). 정규화부 출력 = 계약① finding.

#### 계약 ⑥ 임베딩 모델 + rag_chunk — RAG 적재↔검색 이음새

> 준형 적재 ↔ 진우 검색이 **반드시 같은 임베딩 모델**을 써야 벡터가 맞는다. 모델·차원을 고정 계약으로 박는다.

```json
{
  "chunk_id": "uuid",
  "text": "...",                                   // "컨트롤/룰 1개 = 1청크"(16번)
  "embedding": [/* float[1024] */],
  "embedding_model": "amazon.titan-embed-text-v2:0",  // 고정 — 적재·검색 동일 필수
  "dim": 1024,
  "metadata": { "cloud":"aws|azure|generic", "service":"s3", "framework":"CIS|FSBP|ISMS-P|...",
                "control_id":"INTERNAL-S3-PUBLIC-001", "severity":1, "isms_p":"...",
                "lifecycle":"runtime|build", "remediable":true }
}
```

> `metadata.control_id`가 finding의 `control_id`와 동일 택소노미 → 검색 시 finding→관련 청크 조인. **Titan embed v2 서울(ap-northeast-2) 가용 확인됨.** fallback: 서울 미가용 시 `cohere.embed-multilingual-v3`(동일 dim 1024, 동가격)으로 교체 — cross-region inference는 NAT 트래픽 비용 발생으로 최후 수단.

#### 계약 ⑦ 엔진 에이전트 핸드오프 (case 객체) — 트리아지 게이트 포함

> 에이전트 간 핸드오프를 **단일 case 객체** 패싱으로 통일(이음새 1개로 축소). 각 에이전트가 자기 구간만 채워 다음으로 넘김. 계약②(Evidence→Reasoning)는 이 객체의 `evidence`/`reasoning` 구간.

```json
{
  "case_id": "uuid",
  "finding": { /* OCSF-lite, 또는 상관 시 finding_ids[] */ },
  "stage": "triage|hypothesis|evidence|reasoning",
  "triage": { "priority_score": 0.0, "escalate": false, "reason": "..." },   // ★ 게이트
  "hypotheses": ["..."],
  "evidence": [ /* 계약② evidence[] */ ],
  "reasoning": { "verdict": "", "confidence_score": 0.0, "narrative": "", "rag_refs": [] },
  "model_trace": [ { "stage":"triage", "model":"haiku", "tokens":123 } ]
}
```

> **트리아지 게이트(비용 통제):** `triage.escalate=true`(고위험·attack-path 후보)만 Hypothesis→Evidence 풀 루프로 승급, 나머지는 UC1 설명(control_id 캐시)에서 멈춤 → finding 1000건이라도 풀 루프는 소수. 9번 비용 통제·15번 모델 배정(Haiku/Sonnet)과 직결.
> **`escalate` 판정 기준(확정):** `severity_id ≤ 2`(Critical/High) **OR** `attack_path_id != null`(attack-path 후보 finding). 이 조건 외에는 Triage에서 멈춤.

#### attack-path 상관 규칙 (MVP — 골든 1경로 규칙 기반)

> 계약③(그래프 JSON)을 *무엇이 채우는가*. 커스텀 엔진이 아래 규칙으로 finding을 엮어 노드/엣지 생성(24번 "커스텀 확정"의 알고리즘). MVP는 골든 경로 R1~R5, 규칙 추가로 확장.

| 규칙 | 조건(입력 finding) | 생성 | 엣지 type |
|---|---|---|---|
| R1 침투 | KEV 취약 워크로드 + **그 워크로드를 외부노출시키는 SG**(open-ingress) | 진입 노드 | — |
| R2 측면이동 | 그 워크로드에 과도 IAM/IRSA 권한 | 엣지(진입→과도권한 resource) | `lateral_move` |
| R3 자격증명 탈취 | resource에 평문 시크릿 finding이고 그게 Azure 자격증명 | 엣지(→Azure resource) | `credential_theft`, `cross_cloud:true` |
| R4 데이터 탈취 | 그 권한이 닿는 S3에 public + PII(data) | 엣지(→데이터 노드) | `data_exfil` |
| R5 신원 장악 | 탈취 Azure 자격증명 + Entra 과도권한 App Registration | 엣지(→Entra 노드) | `identity_takeover`, `cross_cloud:true` |

> 상관 = 한 규칙의 *대상*이 다음 규칙의 *조건 resource*가 되면 엣지를 잇는다(체이닝). 체인 길이 ≥ 3이면 severity를 Critical로 격상(독성 조합). 출력은 계약③ JSON, 콘솔은 그걸 읽어 렌더(console 5.1).
>
> **R1 "同 resource"의 실제 매칭 기준(구현 명확화):** KEV finding과 SG finding은 `resource_id`가 다르다(예: `aws:eks_pod:shop/product` vs `aws:security_group:sg-0product1234`) — 문자열 동일이 아니라 **워크로드↔SG 토폴로지 인접**으로 엮는다. 매핑 출처 = 스캐너 리소스 메타데이터(**EKS 파드 → 노드/ENI → attached SG**); 상관 엔진은 각 워크로드 노드에 부착된 SG 집합을 인덱싱해 두고, 그 SG에 open-ingress finding이 있으면 R1을 발화시킨다. **MVP mock**은 이 토폴로지를 명시 선언한다 — 골든 경로의 `shop/product` 파드는 `sg-0product1234` 뒤에 있다고 간주(f1 KEV ↔ f3 open-ingress SG 연결). 실제 배포에선 Prowler/Config의 리소스 관계 필드로 해소.

> **attack-path 상관 계산 트리거:** 정규화부 Lambda가 배치 완료 시 `cnapp.findings.batch.completed` 이벤트를 EventBridge에 발행 → attack-path 상관 Lambda 기동. Prowler Azure 스케줄 완료 후에도 동일 이벤트 발행. 결과는 계약③ JSON으로 DB에 upsert 후 **`cnapp.attackpath.correlation.completed` 이벤트 발행 → Triage Lambda 기동(2-pass 순서 보장 — `attack_path_id`가 DB에 쓰인 뒤 Triage가 시작해야 `attack_path_id!=null` 조건이 유효).**
>
> **실행 순서(2-pass 확정) — §9 UC0와 통일:** ① 정규화 직후 **1차 상관**(R1~R5를 finding 속성만으로 돌려 후보 경로 생성·`attack_path_id` 부여) → ② **트리아지 게이트**가 `severity_id≤2 OR attack_path_id!=null`로 escalate 판정 → ③ escalate된 finding만 **Evidence**가 read-only로 경로 증거 수집 → ④ **2차 상관/Reasoning**이 그 증거로 경로 확정·체인 격상·내러티브 작성. *1차는 규칙(싸고 빠름)으로 후보를 넓게, 2차는 escalate된 소수만 깊게* → 트리아지 게이트(비용 통제)와 정합. (Evidence는 상관의 입력이 아니라 후보 경로의 증거 보강 — 닭/달걀 해소.)

#### 4.4.1 정규화 확정 규칙 3종 (검증서 드러난 §24 항목 닫음)

> 계약①·⑤를 코드로 졸업시킬 때 반드시 필요한 정규화 규칙. 아래로 확정하고 `contracts/` 졸업 시 그대로 스키마/카탈로그 파일로 옮긴다.

**(a) `resource_id` 캐논 규칙** — `{cloud}:{type}:{native_id}`의 `native_id` 표준형을 type별로 고정(스캐너가 ARN이든 이름이든 이 형태로 캐논화 → `dedup_key` 일치 보장).

| resource_type | native_id 표준형 | 예 |
|---|---|---|
| `s3_bucket` | 버킷명 | `aws:s3_bucket:member-pii-prod` |
| `iam_role` | role명(path 제외) | `aws:iam_role:order-irsa` |
| `eks_pod` | `namespace/워크로드명` | `aws:eks_pod:shop/product` |
| `security_group` | sg-id | `aws:security_group:sg-0abc123` |
| `secret_plaintext` | `{보유 워크로드}/{시크릿 키}` (type 세그먼트는 `secret_plaintext` 유지) | `aws:secret_plaintext:shop/order/AZURE_SP_CRED` |
| `app_registration` | appId(client id) | `azure:app_registration:<appId>` |
| `service_principal` | objectId | `azure:service_principal:<objId>` |

> 규칙: ARN은 **마지막 세그먼트만**, 대소문자 보존, 계정ID·리전·path는 native_id에서 제외(같은 리소스를 소스마다 다르게 부르는 것 방지). 신규 type은 이 표에 추가.

**(b) INTERNAL `control_id` 카탈로그 (MVP — 골든 경로 R1~R5 + 6기둥 발화 필수분)** — 소스 무관 내부 ID ← 각 스캐너 native 체크 매핑. `finding.control_id`·`rag_chunks.metadata.control_id`가 이 ID를 공유.

| INTERNAL control_id | 기둥 | 소스 매핑(예) |
|---|---|---|
| `INTERNAL-VULN-KEV-001` | vuln | `inspector:CVE-*`(KEV 등재) · `trivy:CVE-*` |
| `INTERNAL-KSPM-PRIVILEGED-001` | kspm | `kube-bench:5.2.*` · `trivy-k8s:KSV*` |
| `INTERNAL-IAM-OVERPRIV-001` | ciem | `accessanalyzer:*` · `prowler:iam_policy_allows_privilege_escalation` |
| `INTERNAL-SECRET-PLAINTEXT-001` | cspm | `prowler:eks_*_secret_*` · custom(매니페스트 스캔) |
| `INTERNAL-S3-PUBLIC-001` | cspm | `securityhub:S3.8` · `config:s3-bucket-public-read-prohibited` · `prowler:s3_bucket_public_access` |
| `INTERNAL-S3-NOENCRYPT-001` | cspm | `securityhub:S3.4` · `config:s3-bucket-server-side-encryption-enabled` |
| `INTERNAL-DATA-PII-EXPOSED-001` | data | `macie:SensitiveData/*` |
| `INTERNAL-SG-OPEN-INGRESS-001` | cspm | `securityhub:EC2.19` · `prowler:ec2_securitygroup_allow_ingress_from_internet_*` |
| `INTERNAL-ENTRA-OVERPRIV-APP-001` | ciem | `prowler:entra_id_app_*_overprivileged` |
| `INTERNAL-ENTRA-RISKY-CONSENT-001` | ciem | `prowler:entra_id_*_consent_*` |
| `INTERNAL-ENTRA-SP-CRED-001` | ciem | `prowler:entra_id_sp_credential_no_expiry` (f16 — SP 자격 무만료) |
| `INTERNAL-ENTRA-INSECURE-CFG-001` | cspm | `prowler:entra_id_app_redirect_uri_insecure` (f17 — Defender secure-score) |
| `INTERNAL-ECR-SCAN-DISABLED-001` | cspm | `securityhub:ECR.1` · `prowler:ecr_*_scan_*` (f12 — scan-on-push off) |
| `INTERNAL-S3-LOGGING-DISABLED-001` | cspm | `config:s3-bucket-versioning-enabled` · `config:s3-bucket-logging-enabled` (f15) |

> 위는 골든 경로(R1~R5)와 6기둥 발화에 필요한 최소 카탈로그(**14종** — `contracts/control-catalog.json`과 동수). **전체는 `contracts/control-catalog.json`으로 졸업**(ID→{pillar, severity_default, sources[], isms_p, remediable}). 새 스캐너 체크가 추가되면 여기에 매핑 한 줄 추가.

**(c) remediated 판정 스코프(스캐너별)** — 계약⑤ `scan_batch_id`는 **(source, 배치)** 쌍으로 본다. remediated 판정 = *"그 source가 커버하는 control 집합 안에서, 다음 동일 source 배치에 같은 `dedup_key`가 없으면 remediated"*. 예: Trivy 배치는 Config가 잡는 `INTERNAL-S3-*`를 건드리지 않으므로 S3 finding을 remediated로 만들지 않는다. **각 source의 control 커버리지 = (b) 매핑표의 역인덱스**(source → 그 source가 emit하는 INTERNAL control_id 집합). 드리프트(remediated→open 재발)도 같은 스코프로 판정.

### 4.5 우선순위 (시간 쪼들릴 때 기준)

> **1순위 = 에이전틱 엔진의 능동조사** (Evidence/tool use가 한 경로라도 **진짜 작동**) → **2순위 = attack-path 상관** → **3순위 = 스캐너·수집·RAG 토대** → **4순위 = 관제앱·CI/CD·멀티클라우드 포장.**
>
> **"AI가 스스로 API를 호출해 증거를 모아 공격 경로를 판단하는 한 장면"**이 데모의 핵심. 시간이 부족하면 포장(4순위)부터 줄이고 이 한 장면을 사수한다.

**공유 자산(양쪽 함께):** 수집 파이프라인(EventBridge→SQS→Lambda, OCSF 정규화), 에이전틱 엔진 코어(`engine/`), 인프라 골격(계정·IaC·EKS·인증), 관제 대시보드(`apps/console/`).

### 4.6 폴더 구조 & terraform 레이어링 (소유 = 사람 아닌 컴포넌트)

> **원칙:** 폴더는 *사람*이 아니라 *컴포넌트*로 나눈다(`junhyeong/` 같은 폴더 금지 — 소유 바뀌면 깨짐). 소유는 폴더 이름이 아니라 *속성*으로 아래 표에 기록. 각 영역 = 폴더 1개, 영역 안의 반반은 하위 폴더로 쪼개 같은 폴더 내 충돌 방지. 이음새 계약은 전부 `contracts/`에 모음.

**terraform = 레이어드.** `infra/`에서만 apply하고, 컴포넌트 폴더(scanners·pipeline·engine·rag·attackpath·apps)는 **코드만**(CI가 배포). 쪼개기 단위는 **영역까지만**(영역 안 반반까지 또 terraform 만들지 않음 — 한 영역 = state 1개, 두 사람이 그 파일만 공유).

```
1) 기반 먼저:  infra/shared   (VPC·EKS·OIDC·RDS pgvector·Bedrock·ECR)  → 준형, 최초 apply, 모두가 의존
2) 그 위 영역별 terraform (영역 주인이 apply, 의존성 순서대로):
     infra/target     준형   취약 워크로드+의도적 결함 (휘발성 — 토글하며 apply/destroy 잦음, 격리)
     infra/console    진우   ALB·Cognito·console Lambda·SFn·CloudFront
     infra/scanners   각 주인  스캔 IAM 역할·서비스 활성화(Config/SecurityHub/Inspector…)
     infra/pipeline   각 주인  EventBridge·SQS·정규화 Lambda
     infra/engine     각 주인  에이전트 Lambda·Bedrock IAM·Step Functions
```

| 폴더 | 쪼개기(준형/진우) | terraform | 비고 |
|---|---|---|---|
| `contracts/` | **안 쪼갬 — 공유** | ❌ | 모든 이음새 계약(4.4)의 단일 진실. 확정 후 거의 고정 |
| `infra/shared` | 준형 | ✅ 기반 | 최초 apply, 전 영역 의존 |
| `infra/target` | 준형 | ✅ | 휘발성·격리 |
| `infra/console` | 진우 | ✅ | 진우 독립 apply |
| `infra/{scanners,pipeline,engine,rag,attackpath}` | 영역 주인 | ✅ 영역 단위 | 영역 안 반반은 같은 state 공유 |
| `scanners/` | cspm 준형 / workload 진우 | ❌ 코드 | 병렬(둘 다 finding 뱉음) |
| `pipeline/` | ingest 준형 / normalize 진우 | ❌ 코드 | 이음새=계약⑤ |
| `engine/` | core 공유 / triage·evidence 준형 / hypothesis·reasoning 진우 | ❌ 코드 | 핸드오프=계약⑦ |
| `rag/` | corpus 준형 / retrieval 진우 | ❌ 코드 | 이음새=계약⑥ |
| `attackpath/` | model 준형 / correlation 진우 | ❌ 코드 | 상관규칙 4.4 |
| `apps/` | target 준형 / console 진우 | ❌ 코드(인프라는 infra/) | |
| `docs/` `CLAUDE.md` `troubleshooting.md` | **안 쪼갬 — 공유** | ❌ | `troubleshooting.md`=작업 로그(트러블슈팅+진행) 중앙 1개, `[영역]` 태그 한 줄씩(영역별 파일 금지) |

- **같이 쓰는(공유 편집) 파일은 4개뿐:** `contracts/`, `engine/core/`, `docs/`, `CLAUDE.md`. 나머진 단일 소유라 각자 push해도 충돌 없음.
- **apply 자동화(병목 방지):** main push → GitHub Actions가 해당 `infra/<영역>` terraform apply. 진우가 콘솔 인프라 필요 시 *사람(준형)*이 아니라 *파이프라인*을 기다림. console 인프라 *요구사항*은 진우가 명세, 구현·CI는 준형 틀.
- **state 백엔드:** S3 state 버킷 1개 + `infra/<영역>` prefix로 분리(manual-infra.md 2번의 부트스트랩 — shared/target/console 외 scanners/pipeline/engine prefix도 같은 규칙). 영역별 state 격리라 한 명이 apply해도 남의 인프라 안 건드림.
- **과한 선생성 금지:** 폴더 *지도*는 합의하되 실제 폴더·terraform은 그 단계 도달 시 생성(infra/shared부터).

---

## 5. HALO 레퍼런스 모델 & 차별점

레퍼런스(메가존 HALO) 대비 차별점:
1. **멀티클라우드 1급** — AWS+Azure를 OCSF로 통합(이질적 보안 데이터 단일 뷰).
2. **한국 규제 네이티브** — ISMS-P/CSAP 매핑 내장.
3. **에이전틱 자율 조사 루프** — 가설→증거→판정.
4. **오픈소스 스택 투명성** — Prowler/Trivy/Checkov/kube-bench 재현 가능.
5. **Code-to-Cloud** — IaC(빌드) → CI 게이트(배포) → 설정(런타임)까지 Shift-Left + 공급망.

### 5.1 차별점 우선순위 — 핵심 무기 vs 보조

차별점 5개를 강약으로 나누고, 각각 "일반 CNAPP/HALO는 이런데, 우리는 이렇다"를 1줄로 대비한다.

**★★★ 핵심 무기 (이 둘로 승부):**

- **에이전틱 AI 능동 조사** (위 3번) — tool use로 LLM이 스스로 추가 증거를 수집(가설→증거→판정), 단순 설명형 AI와 다름.
  - *대비:* HALO/일반 CNAPP의 AI는 주어진 finding을 **설명·요약**하는 보조형. 우리는 LLM이 **read-only API를 스스로 호출해 증거를 모으고** 판정한다.
- **크로스클라우드 attack-path** (위 1번의 심화) — AWS 워크로드 침해가 **Azure 신원(Entra ID) 장악**으로 번지는 경로를 추적. AWS에서 탈취·노출된 Azure 자격증명이 Entra의 과도권한 앱/계정으로 이어지면 **신원 시스템 전체 통제권**이 넘어간다.
  - *대비:* 대부분은 **단일 클라우드 내부**(특히 AWS) 상관에 머문다. 우리는 **AWS 워크로드→Azure 신원 경계를 넘는 탈취 경로**를 하나의 그래프로 잇는다.

**★★☆ 보조 (핵심을 받쳐주는 차별점):**

- **한국 규제 네이티브** (위 2번) — ISMS-P/CSAP 매핑 내장.
  - *대비:* 상용 글로벌 도구는 **CIS/NIST 중심에 한국 규제는 애드온**. 우리는 ISMS-P/CSAP를 RAG·매핑에 **처음부터 내장**한다.
- **오픈소스 투명성** (위 4번) — Prowler/Trivy/Checkov/kube-bench 기반으로 재현 가능.
  - *대비:* 상용은 **블랙박스 엔진**. 우리는 룰과 결과가 **오픈소스라 누구나 재현·검증** 가능하다.
- **Code-to-Cloud / Shift-Left** (위 5번) — 배포 전 단계에서 차단.
  - *대비:* 다수는 **운영(런타임) 설정 점검 중심**. 우리는 IaC·CI 게이트로 **배포 전에(Shift-Left)** 막고 공급망까지 본다.

### 5.2 포지셔닝 한 문장

> HALO가 운영 단계의 클라우드를 점검·통합하는 상용 플랫폼이라면, 우리는 거기에 AI 능동 조사·크로스클라우드 추적·Shift-Left를 더한 **'AI가 스스로 조사하고 코드 단계부터 막는 멀티클라우드 CNAPP'**이다.

### 5.3 "HALO 짝퉁 아니냐"는 질문 대비 (면접용)

> HALO를 베낀 게 아니라 **레퍼런스로 삼아 MSP의 실제 사업(멀티클라우드 CSPM·CNAPP·attack-path·AI 보안)을 이해하고 출발**한 것입니다.
> 똑같이 만든 게 아니라, HALO가 약하거나 안 하는 지점을 골라 **에이전틱 AI 능동 조사·크로스클라우드 attack-path·Shift-Left(Code-to-Cloud)**로 차별화했습니다.
> 즉, 같은 문제 공간을 **다른 관점과 더 깊은 자동화**로 푼 결과물입니다.

### 5.4 솔직한 전제

> 우리는 **2인·2주 포트폴리오**이고 HALO는 상용 제품이다. 따라서 차별점의 본질은 *"HALO보다 낫다"*가 아니라 **"HALO가 약하거나 안 하는 영역을 다른 관점으로 한다"**이다.

아래 표는 HALO 각 구성요소에 대한 우리 대응과 채택 여부를 매핑한 것이다.

| HALO 구성 | 우리 대응 | 채택 |
|---|---|---|
| A&R (설정·권한·데이터 점검+개선) | CNAPP 본체 + remediation | ✅ 핵심 |
| NOVA (보안 단일 화면 통합) | 통합 관제 대시보드 | ✅ 핵심 |
| AI 보안 거버넌스 | 에이전틱 엔진 + OWASP-LLM 가드레일 | ✅ 핵심 |
| 워크로드·공급망(HALO 약점) | Shift-Left·KSPM·SBOM·서명 | ✅ 차별점 |
| AI 보안관제(SOC)·CWPP 런타임 | 위협탐지·런타임 | ⚠️ 확장만 |

---

## 6. 🏗️ 멀티클라우드 구도 — AWS(워크로드) / Azure(신원)

### 6.1 시나리오 (강점 기반)
> 고객사 커머스는 **워크로드는 AWS**(컨테이너·클라우드 네이티브 강점), **신원·인증은 Azure Entra ID**(Microsoft 365 생태계)에 둔다. **회원 PII 등 데이터는 AWS S3에만 보관**한다(Azure에는 데이터를 두지 않음 — 중복 저장은 명분이 약함). 우리 CNAPP은 이 분산 환경을 한 화면에서 점검하고, **AWS 워크로드 침해가 Azure 신원(Entra ID) 장악으로 번지는 크로스클라우드 공격 경로**까지 추적한다.

이 분업 덕에 (a) "왜 Azure?"가 자연스럽고(Microsoft 365 = 신원이 Azure), (b) SSO가 곁다리가 아니라 시나리오 중심축이 되며, (c) Entra 자체를 CIEM으로 점검하는 것(과도권한 앱 등록·위험한 consent·권한상승 경로)이 정당해진다.

### 6.2 비중

아래 표는 AWS와 Azure의 정체성·점검 깊이·비중을 대비한 것이다.

| 구분 | AWS (워크로드 주인) | Azure (신원의 주인) |
|---|---|---|
| 정체성 | 컨테이너 워크로드 + 데이터(회원 PII는 AWS S3) | Microsoft 생태계 신원(Entra ID) |
| 점검 깊이 | 풀 CNAPP 6기둥 | **Entra CIEM**(과도권한 앱 등록·위험한 consent·권한상승) + Defender for Cloud secure score(멀티클라우드 통합 뷰) |
| 비중 | 80% | 20% |

> Azure를 AWS와 대칭으로 만들지 않는다(과함). "의미 있는 조연" 수준 — 미끼가 아니라 시스템의 진짜 일부(신원). 데이터는 Azure에 두지 않으므로 Azure 점검은 **신원(Entra) + 리소스 secure score**에 집중한다.

---

## 7. 🏗️ CNAPP 기둥 + attack-path

아래 표는 CNAPP 각 기둥의 점검 내용·핵심 서비스·티어를 정리한 것이다.

| 기둥 | 내용 | 핵심 서비스 | 티어 |
|---|---|---|---|
| **CSPM** (설정 자세) | 설정 위반·드리프트·컴플라이언스 | Config, Security Hub CSPM, Prowler | 핵심 |
| **CIEM** (권한) | 과도/미사용 권한·상승 경로 (AWS IAM + **Azure Entra ID**: 과도권한 앱 등록·위험한 consent) | IAM Access Analyzer, Entra ID | 핵심 |
| **취약점 관리** | 이미지·워크로드 CVE, KEV 우선순위 | Inspector, Trivy | 핵심 |
| **KSPM** (쿠버네티스 자세) | K8s 설정·Pod Security·RBAC | kube-bench(CIS K8s) | 핵심 |
| **데이터 보안(DSPM 맛)** | 민감데이터 위치·노출 (**AWS S3 전용**) | Macie (AWS S3 전용) | 강추 |
| **attack-path** (상관) | 위 기둥 묶어 탈취 경로(크로스클라우드 포함) | 새 Security Hub(exposure) + 커스텀 그래프 | 핵심 |
| **CWPP** (런타임) | 런타임 위협·이상행위 | GuardDuty Runtime / Falco | 확장(훅만) |

> CWPP 런타임은 SOC 경계·범위·가성비 이유로 배제하되, OCSF 스키마·대시보드에 "runtime" 자리만 비워둬 추후 입력 연결 시 반나절~하루에 추가 가능.

---

## 8. 🏗️ 애플리케이션 구조 (앱 2개)

### 8.1 타깃 앱 (고객사 워크로드 — 점검 대상)
- **역할:** 일부러 취약하게 설정된 고객사 시스템. findings 소스.
- **AWS:** 커머스 마이크로서비스 **3개(product · order · member)** + EKS. **회원 PII는 AWS S3 버킷에만 보관.** 서비스 목록은 target-app-design.md 1번 확정 — 결제 서비스 없음.
- **Azure:** Microsoft Entra ID(직원 신원 디렉터리) + App Registration(SSO 연동). **민감데이터는 두지 않음** — Azure는 신원의 주인. 결함은 과도권한 앱 등록·위험한 consent 등 **신원 결함**으로 심는다.
- **원칙:** 기능은 평범, **취약점은 IaC에 심음**(코드 버그 아님). Bedrock·SSO 없음.

### 8.2 관제 앱 (우리 플랫폼 — HALO 같은 메인 앱)
- **역할:** posture·findings·attack-path를 보여주는 얼굴. NOVA 대응.
- **화면:** 보안점수(AWS+Azure secure score 나란히), finding 목록(6종), attack-path 그래프, 각 finding의 AI 설명·조치안.
- **여기에 Bedrock·SSO가 들어감.**

### 8.3 관제 앱이 점검하는 것
고객사 앱의 *코드가 아니라 그 앱이 깔린 클라우드 환경*:
CSPM(S3·SG·IAM·암호화) · CIEM(AWS 과도 권한 + **Azure Entra 과도권한 앱·위험한 consent**) · 취약점(이미지 CVE) · KSPM(Pod Security·RBAC) · 데이터(**AWS S3** 민감데이터 노출) · attack-path(**AWS 워크로드→Azure 신원** 크로스클라우드 탈취 경로).

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
| **0** | **Evidence 능동 수집 (tool use)** | Triage가 finding을 넘기면 LLM이 **추가로 무엇을 봐야 할지 스스로 판단**해 read-only API 호출(`getBucketPolicy`·`getBucketAcl`·Macie 분류 결과·IAM 정책 조회 등)로 검증·보강. **2-pass(4.4): 1차 규칙상관(R1~R5)이 `attack_path_id` 부여 → escalate된 finding의 경로 증거를 Evidence가 채움 → 2차 상관/Reasoning이 확정.** Evidence는 상관의 *입력*이 아니라 후보 경로의 *증거 보강*. | **★ 챗봇 탈출 최소조건** (15번 Evidence 에이전트와 직결) |
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
  → ALB(authenticate-cognito)가 미인증이면 Cognito로 리다이렉트
  → Cognito가 Entra ID로 페더레이션 (Entra = IdP)
  → Entra 로그인 성공 → Cognito 토큰 발급 → 관제 앱 진입
```

- **역할:** Entra ID = IdP(신원), Cognito = SP/허브(AWS), 관제 앱 = Cognito 신뢰.
- **무료 가능 근거:** 기본 SAML SSO는 Entra 전 티어 무료(커스텀 앱 포함, 앱 1개 = 무료 10개 한도 내). 조건부 액세스·그룹 프로비저닝 등 P1/P2 기능 미사용. SP-initiated 흐름이라 보안 권장 방식과도 일치.
- **검증:** Week 1에 실제 테넌트로 SSO 우선 검증(이론상 무료지만 테넌트 상태 직접 확인).
- **구현:** ALB `authenticate-cognito` 액션(Cognito 전용, 클라이언트 시크릿 불필요)으로 앱 코드에 인증 로직 최소화.

---

## 11. ✅ 핵심 설계 결정

### 기반

아래 표는 계정·인증·CI/CD 등 기반 영역의 결정(D1~D13)과 근거를 정리한 것이다.

| # | 결정 | 왜 |
|---|---|---|
| D1 | 새 계정 + **단일 계정**(Organizations 미사용) | 무료 플랜에서 Organizations 켜면 유료 전환·크레딧 소멸. |
| D2 | **단일 리전(서울)** + CloudTrail/Config **전 리전 수집** | 비용↓, 단 리전 드리프트 탐지는 전 리전. |
| D3 | **IAM 어드민 + MFA, 루트 잠금**(Identity Center 미사용) | Identity Center는 Organizations 동반 → 크레딧 소멸 회피. |
| D4 | CI/CD **GitHub OIDC → IAM Role**(AWS, 키 없음) + **Entra Workload Identity Federation**(Azure, 키 없음) | AWS는 GitHub OIDC→IAM Role, Azure는 App Registration에 Federated Identity Credential 등록 → GitHub Actions가 client-secret 없이 Azure 인증. 양쪽 모두 장기 자격증명 없는 키리스. |
| D5 | 파드 **IRSA / Pod Identity** | 스코프된 임시 자격증명. |
| D6 | **EKS + ArgoCD GitOps** | 배포·CI/CD 목표 핵심. |
| D7 | **앱 2개**(취약 타깃 + 관제 대시보드) | findings 소스 + NOVA 대응. |
| D8 | **취약점은 IaC에 심음** | 설정 검사 대상. 앱 부담 최소. |
| D9 | **Bedrock + 수동 RAG**(SageMaker 미사용) | ML 오버·비용 회피, 직접 조립로 깊이. |
| D10 | **앱 SSO는 Cognito**(Entra→Cognito→OIDC) | 워크포스 SSO 크레딧 문제 회피 + 멀티클라우드 신원. |
| D11 | **Azure = Entra CIEM 중심 + Defender for Cloud 보조** | Prowler entra_id_* 체크로 과도권한 앱·위험한 consent·권한상승 탐지(핵심). Defender for Cloud는 리소스 secure score 보조. Security Hub는 AWS 전용. |
| D12 | **Prowler 병행** | 오픈소스 멀티클라우드 스캐너. |
| D13 | **에이전틱 엔진 = 멀티에이전트** | 가설→증거→추론 루프. |

### 워크로드·Shift-Left (티어링)

아래 표는 워크로드·Shift-Left 영역의 결정(D14~D19)과 티어를 정리한 것이다.

| # | 결정 | 티어 |
|---|---|---|
| D14 | 취약점 스캔 빌드 단계로(CI Trivy + 런타임 Inspector) | 핵심 |
| D15 | CI 게이트(Checkov/OPA로 미스컨피그 IaC 머지 전 차단) | 핵심 |
| D16 | KSPM(kube-bench로 CIS K8s 점검) | 핵심 |
| D17 | 공급망(cosign 서명 + SBOM, ArgoCD 미서명 거부) | 보너스 |
| D18 | CWPP 런타임 배제(훅만) | 확장 |
| D19 | 공유 엔진 코어 + 도메인 로직 분리 | 핵심 |

---

## 12. 🏗️ 아키텍처

```
[입력: CNAPP 신호]
  AWS 설정:   Config · Security Hub CSPM · Prowler · Macie
  AWS 워크로드: Inspector · Trivy · kube-bench(KSPM) · IAM Access Analyzer(CIEM)
  AWS 빌드게이트: CI에서 Checkov/OPA(IaC) · Trivy(이미지)
  Azure:      Prowler(Azure 모드 — OCSF 출력 → S3 → EventBridge → 기존 파이프라인 합류)
              └─ Entra CIEM: entra_id_* 체크(과도권한 앱·위험한 consent·권한상승)
              └─ Defender for Cloud: 리소스 secure score
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
   [attack-path 그래프] 권한+취약점+설정+데이터 → 탈취 경로(AWS 워크로드→Azure 신원 크로스클라우드)
            │
   위반/위험 → 자동 개선 제안 → 휴먼인더루프(승인) → Step Functions → 불변 감사로그(S3 Object Lock)
            │
[관제 앱]  posture 점수(AWS+Azure) + findings + attack-path + AI 설명/조치 (React, S3+CloudFront)
[타깃 앱]  AWS 커머스(EKS, 회원 PII는 S3) + Azure Entra ID(신원·과도권한 앱) ← findings 소스
[CI 게이트] GitHub Actions(OIDC) → Checkov/Trivy → (cosign*) → ECR → ArgoCD → EKS
[인증]     Entra ID ─SAML─▶ Cognito ─OIDC─▶ ALB(authenticate-cognito) → 관제 앱
[관측]     kube-prometheus-stack + 로그 파이프라인
```

---

## 13. 서비스 구성 — AWS

아래 표는 AWS 측 서비스를 티어(필수·강추·보너스·선택·확장)별로 정리한 것이다.

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
| | Bedrock + 벡터DB | 에이전틱 RAG(**pgvector, RDS PostgreSQL t3.micro** — 24번 확정) |
| | Step Functions | 승인 포함 조치 |
| | EKS + ECR + ArgoCD | 워크로드·배포·GitOps |
| | Cognito | 앱 SSO 허브(SP) |
| 강추 | Macie | 데이터 보안(**AWS S3 민감데이터 전용**) |
| | Secrets Manager + KMS | 시크릿·암호화 |
| | CloudFront + S3 | 관제 앱 정적 호스팅 |
| 보너스 | cosign / Syft | 이미지 서명·SBOM |
| 선택 | SNS / Teams 웹훅 | 알림 |
| 확장 | GuardDuty (Runtime) | attack-path 보조 / CWPP 훅 |

---

## 14. 서비스 구성 — Azure

아래 표는 Azure 측 서비스를 티어별로 정리한 것이다.

| 티어 | 서비스 | 역할 | 비고 |
|---|---|---|---|
| 필수 | Microsoft Entra ID | **신원의 주인** — 인증(SSO IdP) + **CIEM 점검의 핵심 대상**(과도권한 앱 등록·위험한 consent·권한상승 경로) | 무료 티어. 회사 디렉터리 = 크로스클라우드 attack-path **종착지** |
| | App Registration / Service Principal | SSO 연동 + **과도권한·위험한 consent CIEM 점검 대상** | 어차피 SSO로 생성, 결함을 여기 심음 |
| | Defender for Cloud | Azure 리소스 CSPM — secure score·권고·컴플라이언스(멀티클라우드 통합 뷰) | AWS Security Hub 대응. **데이터 탐지(sensitive data discovery)는 쓰지 않음** — Azure는 데이터 저장소가 아님 |
| 강추 | Azure Policy | 리소스 규정 준수 평가 | Defender 연계, 컴플라이언스 매핑 |
| 선택 | Log Analytics Workspace | Defender/Entra 로그 수집·쿼리 | findings 파이프라인 연동 시 |

**Prowler Azure 스캔 스케줄:** GitHub Actions cron `0 17 * * *`(UTC = 매일 새벽 2시 KST) → OCSF 출력 → S3 → EventBridge S3 이벤트 → 기존 SQS→Lambda 파이프라인 합류. 인증은 D4 Entra Workload Identity Federation(키 없음).

**의도적 미스컨피그(Azure — 신원 중심, 4~5개):** ① 과도권한 App Registration(예: `Directory.ReadWrite.All` 등 디렉터리 광범위 권한), ② 위험한 consent grant(검증 안 된 앱에 광범위 위임), ③ Entra 권한상승 경로(과도한 디렉터리 역할 할당), ④ Service Principal에 만료 없는/유출 위험 자격증명, ⑤ (선택) Defender secure score를 깎는 일반 리소스 미스컨피그. **Storage/Blob 등 데이터 결함은 심지 않음** — 데이터는 AWS S3에만 있고 Azure는 신원만 다룬다.

---

## 15. 에이전틱 엔진 — 공유 코어 + 도메인 로직

아래 표는 각 에이전트의 공통 역할과 설정·워크로드 도메인별 분담을 정리한 것이다.

| 에이전트 | 공통 역할 | 설정 도메인 | 워크로드 도메인 | Bedrock 모델 |
|---|---|---|---|---|
| Orchestrator | 파이프라인·핸드오프 | (공유) | (공유) | Haiku |
| Triage | enrichment·우선순위 | 설정 finding | 취약점/권한 finding | Haiku |
| Hypothesis | 가설 생성 | 컴플라이언스 위반 영향 | attack-path(권한+취약점+설정) | Sonnet |
| Evidence | read-only 검증 | 관련 설정 확인 | 이미지·워크로드·권한 확인 | Haiku |
| Reasoning | 종합·신뢰점수·리포트 | 컴플라이언스 리포트 | 공격경로 리포트·우선순위 | Sonnet |

> 모델: Haiku 계열(고빈도 분류·파싱·라우팅), Sonnet 계열(추론·내러티브 품질 중요). 데모 finding 100건 처리 기준 예상 비용 $1~3.
>
> ⚠️ **모델 ID 주의(구현 시 확정):** 위 `claude-haiku-4-5`·`claude-sonnet-4-6`는 **Anthropic API의 별칭일 뿐 Bedrock invoke ID가 아니다.** Bedrock 호출은 `anthropic.claude-haiku-4-5-YYYYMMDD-v1:0` 형식의 **모델 ID 또는 서울(ap-northeast-2) 리전 inference profile ARN**을 써야 한다(bare name·date suffix 없는 ID는 **404**). 정확한 ID는 구현 시 `aws bedrock list-foundation-models`로 리전 가용 모델을 조회해 확정한다.

---

## 16. RAG 코퍼스

- **A. 기준·표준(필수):** CIS AWS/Azure/Kubernetes Benchmark, AWS FSBP, Well-Architected 보안. ※ CIS 재배포 금지 → private.
- **B. 조치(필수):** Security Hub 컨트롤 레퍼런스, AWS 서비스별 베스트프랙티스, Defender 권고, Prescriptive Guidance.
- **C. 위협·우선순위(강추):** MITRE ATT&CK(Cloud·Containers), CISA KEV, OWASP Top 10.
- **D. 한국 규제(차별화):** ISMS-P, CSAP, 개인정보보호법 요약.
- **E. 자체 작성(필수):** remediation 플레이북, 조치 카탈로그(allowlist+승인), 심각도 루브릭, 취약점 트리아지 루브릭(KEV+EPSS), 운영 런북, **Azure Entra CIEM 탐지 룰북**(① 고위험 App Registration 권한 목록 — `Directory.ReadWrite.All`, `RoleManagement.ReadWrite.Directory` 등, ② 위험한 consent grant 판단 기준 — `User.ReadWrite.All`, `Mail.ReadWrite` 등, ③ Prowler entra_id_* 체크 ID → 내부 `control_id` 매핑표).
- **F. 스키마(선택):** ASFF/OCSF, Prowler/Trivy/Checkov 룰 정의.
- **G. 워크로드/공급망:** 컨테이너 보안 가이드, Pod Security Standards, SLSA, Sigstore.

청킹: "컨트롤/룰 1개 = 1청크" + `{cloud, service, framework, control_id, severity, isms_p, remediable, lifecycle}`.
MVP 코퍼스: A(CIS AWS+K8s) + FSBP + C(KEV) + E(자체 루브릭).

---

## 17. 🔒 거버넌스 & AI 안전

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
5. **attack-path 골든 시나리오** — 취약파드(KEV CVE)+과도 IRSA 권한+평문 시크릿의 Azure 자격증명+공개 S3(PII)+Entra 과도권한 앱을 동시 심기 → **AWS 워크로드 침투 → 평문 시크릿에서 Azure 자격증명 발견 → 공개 S3로 AWS PII 탈취 → 탈취 자격증명으로 Azure Entra ID 신원 장악**을 하나의 크로스클라우드 탈취 경로로 묶는지(데모 하이라이트). ※ MVP는 이 경로를 **분석·시각화**하는 수준이고, 실제 AWS→Azure 횡단 동작 구현은 보너스.

도구: CloudGoat/AWSGoat/Terragoat 패턴으로 취약 IaC 구성(정답지). golden findings 세트로 CI 회귀 테스트.

---

## 20. KPI

아래 표는 프로젝트 성과를 측정할 지표와 목표를 정리한 것이다.

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

## 21. 🗓️ 개발 로드맵 (2주 압축 · 2인 병렬)

> 아래 Day별 타임라인은 **4.3 의존성 순서**(0 공유인프라 → 1 앱·모니터링 → … → 7 데모)를 달력에 펼친 것이다. 분담·병목·합의 인터페이스는 [4번 작업 분담](#4-작업-분담-균형안--효율용-트랙)이 기준이고, 시간이 쪼들릴 때의 컷 순서는 **4.5 우선순위**(엔진 능동조사 사수)를 따른다.

### Week 1 — 뼈대 + 핵심 루프
| Day | 준형(설정·CI/CD) | 진우(워크로드·관측) |
|---|---|---|
| 1–2 | 계정·Terraform 골격, Config/Security Hub/Prowler 활성화, **SSO 검증** | EKS·ArgoCD·ECR 골격, 취약 타깃앱 배포 |
| 3–4 | 공유 수집 파이프라인·OCSF 정규화 | Inspector/Trivy 연동, 이미지 취약점 finding |
| 5 | **Bedrock finding 설명(RAG #1) 작동** | kube-bench(KSPM), CIEM 신호 |

### Week 2 — 깊이 + 멀티클라우드 + 마감
| Day | 준형 | 진우 |
|---|---|---|
| 6–7 | 우선순위 정렬(#2)·관제 대시보드 v1 | attack-path 그래프 1차, 관측 스택 |
| 8 | **Azure Defender + Entra 통합(멀티클라우드)** | 크로스클라우드 attack-path 시나리오 |
| 9 | Shift-Left CI 게이트 + 자동개선 1~2종(HITL) | 워크로드 finding 대시보드 연계 |
| 10 | 데모 완성 + KPI 측정 + 스크린샷/영상 | 〃 |

**범위 컷라인(무엇을 만드나):** ① 절대사수 = CSPM 본체+RAG 설명+대시보드+Azure(Entra) 통합+Shift-Left+KSPM ② 보너스 = 공급망 서명, attack-path 정교화, ISMS-P 리포트 ③ 확장 = CWPP 런타임, SOC.
**시간 컷 순서(쪼들릴 때 무엇부터 포기하나):** 4.5 우선순위를 따른다 — **엔진 능동조사(1) > attack-path 상관(2) > 스캐너·수집·RAG 토대(3) > 관제앱·CI/CD·멀티클라우드 포장(4).** "AI가 스스로 증거를 모아 공격 경로를 판단하는 한 장면"을 끝까지 사수.
**이후:** 개발 종료 → PPT·문서·발표.

---

## 22. 💰 비용 · 무료 티어 가드레일

- 크레딧 소멸 트리거: **Organizations / Identity Center / Control Tower → 절대 안 켬.**
- Config·Security Hub·Inspector·Macie·Defender는 종량제 → **데모 기간만 켜고 `destroy`.** 서비스별 1일 추정: Config ~$0.30, Security Hub ~$0.03, Inspector ~$0.01, Macie 첫 달 무료(이후 $1/버킷), Defender ~$0.02/서버/시간.
- **EKS:** NAT Gateway 제거 → **NAT Instance(t3.nano, ~$3.40/월) + S3·DynamoDB Gateway Endpoint(무료)** 조합. ※ Interface VPC Endpoint는 개당 $7.30/월 — 6개 시 $43.80/월로 NAT Gateway($32.85)보다 비쌈. **spot + 작은 노드(t3.small×2)**, 비데모 시 **노드 스케일-0**(Cluster Autoscaler minSize=0), 완전 비사용 시 `terraform destroy`, **Budgets 알림($50/$100)**.
- **DB: RDS PostgreSQL t3.micro + pgvector** (Aurora 미사용 — idle 최소 $43/월). free tier 12개월. 이후 ~$13/월. 비데모 시 **RDS Stop**(최대 7일 자동유지, 이후 재시작) → 스토리지만 $0.115/GB/월(20GB ≈ $2.30/월). **7일 자동 재기동 방지: EventBridge Scheduler(daily 새벽 2시 KST) + Lambda → RDS 상태 확인 후 `available`이면 자동 Stop.** infra/shared 포함, 비용 ~$0.
- Azure: Entra ID 무료 티어(신원·App Registration), 컴퓨팅·스토리지 미사용으로 사실상 $0, Defender 소액(데모만).
- 오픈소스(Trivy·Checkov·kube-bench·cosign)는 컴퓨팅 비용만.
- 인증 레이어(Cognito·IAM·Entra 무료)는 사실상 $0.
- **목표 idle 비용(EKS destroy + RDS stop):** ALB ~$6 + S3·CF ~$1 + Secrets Manager ~$2 + RDS storage ~$2.30 = **~$11/월**. EKS 켤 때: 컨트롤플레인 $72 + 노드 ~$8(spot) 추가.

---

## 23. 확장 방향 (본체 아님)

- **CWPP 런타임** — OCSF 스키마·대시보드에 자리만 비워둠 → GuardDuty Runtime/Falco 입력 연결 시 반나절~하루.
- **탐지/SOC** — 같은 엔진에 위협 알림 입력 추가 시 인시던트 트리아지로 확장.
- **자율성 점진 확대** — 신뢰점수 높은 저위험부터 자동 개선 범위 확대.
- **GCP 추가** — Security Command Center로 3-클라우드.
- **Azure 자동개선** — Azure Policy 기반 remediation.

---

## 24. ❓ 미확정 (다음에 닫을 것)

- [x] **프로젝트 명칭 = "에이전틱 AI 기반 멀티클라우드 CNAPP 보안 플랫폼"** (잠정 — 바뀔 수 있음) / 레포 = `cnapp-agentic`(사용 중). → **§24 전부 닫힘, 열린 설계 미확정 0건**(UC5 PDF는 console §14 보너스).
- [x] **레포 = 모노레포 확정** — 단일 레포(`cnapp-agentic`) 안에 `apps/`·`engine/`·`infra/` 폴더로 관리. 레포가 하나여도 배포는 폴더별로 분리(target=EKS, console=S3+Lambda). 모듈 경계 = 폴더 분리 + Terraform state를 `infra/{shared,target,console}`별로 분리. 2인·2주엔 멀티레포보다 모노레포가 정답(pull 한 번, 문서·코드 동거).
- [x] **타깃 앱 마이크로서비스 세부 확정** — product·order·member 3개, 기능·결함·골든 attack-path 전체 목록은 [target-app-design.md](target-app-design.md)가 SSOT.
- [x] **벡터DB = pgvector (RDS PostgreSQL t3.micro)** 확정 — 코퍼스 규모 작아 OpenSearch Serverless는 오버스펙·고비용. Aurora는 idle $43/월로 과함. RDS PostgreSQL t3.micro(free tier 12개월, 이후 $13/월)로 확정. 저렴·단순·finding 메타데이터와 동거 가능.
- [x] **Azure 역할 = 신원(Entra ID) 중심 확정** — 데이터(회원 PII)는 **AWS S3 전용**, Azure에는 데이터를 두지 않는다(중복 저장은 명분 약함). Azure 점검은 Entra CIEM(과도권한 앱·위험한 consent·권한상승) + Defender for Cloud secure score. Macie는 AWS S3 전용, Defender의 데이터 탐지는 미사용.
- [x] **MVP 데모 골든 시나리오 = 크로스클라우드 신원 탈취 경로 확정** — product 취약 이미지 침투 → order 평문 시크릿에서 Azure 자격증명 발견 → member 공개 S3로 AWS PII 탈취 → 탈취 자격증명으로 Azure Entra ID 과도권한 앱/계정 장악. MVP는 이 경로를 **분석·시각화**하는 수준, 실제 AWS→Azure 횡단 동작은 보너스.
- [x] **attack-path 계산 = 커스텀 엔진 상관 확정** — 새 Security Hub exposure는 AWS 내부만 엮고 Azure를 못 덮어 크로스클라우드(AWS→Azure) 경로를 단독으로 못 그림 → 선택지가 사실상 커스텀뿐. 우리가 규칙 기반으로 finding을 엮어 4.4 계약 ③ 형식으로 출력(MVP는 골든 1경로 규칙, 규칙 추가로 확장). 콘솔 렌더링은 커스텀 postgres 인접 리스트(console 5.1).
- [x] **Azure findings 파이프라인 진입 = Prowler(Azure 모드) 확정** — Prowler가 AWS·Azure 모두 지원(entra_id_* 체크·Defender 연동), OCSF 포맷 출력. GitHub Actions 스케줄 실행 → S3 저장 → EventBridge S3 이벤트 → 기존 SQS→Lambda 파이프라인 합류. 별도 Azure Event Grid·Function 불필요.
- [x] **자동 조치 카탈로그 1차 범위 확정(MVP 3종)** — ① S3 Public Access Block(1 API, 가역, 고임팩트) ② Security Group 0.0.0.0/0 인바운드 제거(특정 포트 룰 삭제) ③ IAM 최소권한 diff 제안(실제 사용 권한 기반 축소 정책 생성 — 승인 후 적용). ①②는 HITL 승인 후 자동 실행, ③은 제안만. Azure findings는 가이드 텍스트 + "수동 조치 필요" 표시(자동 실행 없음). console-app-design.md §14 동기화.

**검증에서 새로 드러난 미확정 → 4.4.1로 확정(closed):**
- [x] **`resource_id` 정규화 규칙 확정** — type별 `native_id` 표준형 표로 고정(4.4.1 a). ARN은 마지막 세그먼트만·대소문자 보존 → `dedup_key` 일치 보장.
- [x] **INTERNAL `control_id` 카탈로그 확정** — 골든 경로 R1~R5 + 6기둥 발화 필수분 매핑표(4.4.1 b), 전체는 `contracts/control-catalog.json`으로 졸업.
- [x] **remediated 판정 스코프(스캐너별) 확정** — `scan_batch_id`=(source,배치), 판정은 *그 source가 커버하는 control 집합* 안에서만(4.4.1 c) → 이종 스캐너 오판 방지.

---

*v5 — 멀티클라우드(AWS 워크로드 / Azure 신원·데이터) 강점 분업, 앱·Bedrock·SSO·테스트 확정. 명칭·레포·세부는 다음 단계.*

*변경 요약(v5.1): **Azure 역할을 데이터→신원(Entra ID) 중심으로 전면 전환.** 회원 PII는 AWS S3 전용, Macie도 AWS S3 전용 명시(Defender 데이터 탐지 미사용). Azure 점검은 Entra CIEM + Defender secure score. 골든 시나리오를 크로스클라우드 신원 탈취 경로(AWS 워크로드→Azure Entra 장악)로 교체, MVP는 분석·시각화 수준/횡단 동작은 보너스. 미확정에서 Azure 역할·골든 시나리오 닫음. 문서 식별 헤더 추가.*

*변경 요약(v5.2): **작업 분담을 균형안으로 갱신**(4번) — 각 영역(스캐너·수집·엔진·RAG·attack-path)을 반반 갈라 양쪽이 핵심을 다 만지게. 의존성 순서(4.3)·합의 인터페이스 2개(OCSF 스키마·엔진 입출력, 4.4)·시간 컷 우선순위(엔진 능동조사 사수, 4.5) 추가. 로드맵(21번)을 이 분담·우선순위와 정합되게 갱신.*

*변경 요약(v5.3): 작업 분담 표를 **하나로 통합**(앱·토대=확정 / 핵심 영역=협의중을 한 표의 상태 열로) + **담당을 실명(준형·진우)으로 교체.** 분담은 상시 협의로 계속 조정되는 살아있는 문서임을 명시. 의존성·인터페이스·우선순위는 그대로 유지.*

*변경 요약(v5.4): **비용 최적화 + 설계 잔여 갭 해소.** ① Aurora→**RDS PostgreSQL t3.micro** 확정(22·24번). ② NAT 전략: NAT Gateway 제거 → **NAT Instance(t3.nano)+S3·DynamoDB Gateway Endpoint**(22번). ③ Azure findings 진입 경로 = **Prowler(Azure 모드)** 확정(12·24번). ④ 에이전트별 **Bedrock 모델 배정**(Haiku/Sonnet, 15번). ⑤ **CIEM 분담 독립 행** 추가(4.1). ⑥ **Entra CIEM 탐지 룰북** RAG 코퍼스 E항목 추가(16번). ⑦ D11·13번 표현 갱신(Entra 중심·OpenSearch 잔재 제거). ⑧ 8.1 마이크로서비스 3개 확정.*

*변경 요약(v5.5): **검증 후속 확정.** ① **4.4.1 정규화 확정 규칙 3종** 신설 — (a) `resource_id` 캐논 규칙(type별 native_id 표준형) (b) INTERNAL `control_id` 카탈로그(골든 R1~R5+6기둥, `contracts/control-catalog.json` 졸업) (c) remediated 스코프(source별 control 커버리지). ② §24 해당 3건 닫음. ③ attack-path **2-pass 순서**·핵심 영역 분담을 **확정**으로 전환(진우 검증 완료). ④ `severity_id` 주석 정정. README 폴더구조·docs 안내 갱신.*
