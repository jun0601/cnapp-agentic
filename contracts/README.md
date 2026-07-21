# contracts/ — 공통 이음새 계약 (SSOT)

> 이 폴더는 컴포넌트(scanners·pipeline·engine·rag·attackpath·apps/console) 사이를 잇는 **공통 계약의 단일 진실**이다.
> 설계 근거는 [docs/project-draft.md](../docs/project-draft.md) **4.4(계약 7종)·4.4.1(정규화 규칙 3종)**. 산문이 바뀌면 4.4를 먼저 고치고 여기 파일을 맞춘다(코드가 이 파일을 직접 import → drift 없음).

## 계약 스키마 (JSON Schema, draft 2020-12)

| 파일 | 계약 | 누가 쓰나 |
|---|---|---|
| [finding.schema.json](finding.schema.json) | ① OCSF-lite finding | 정규화→엔진→콘솔 (공통 코어) |
| [case.schema.json](case.schema.json) | ⑦ 엔진 case 핸드오프(② Evidence→Reasoning 포함) | engine 5종 |
| [attack-path.schema.json](attack-path.schema.json) | ③ attack-path 그래프 | attackpath 상관 → 콘솔 렌더 |
| [evidence-allowlist.json](evidence-allowlist.json) | ④ Evidence read-only 툴 allowlist | engine(Evidence) |
| [ingest-envelope.schema.json](ingest-envelope.schema.json) | ⑤ 수집 봉투 | scanners·pipeline(ingest↔normalize) |
| [rag-chunk.schema.json](rag-chunk.schema.json) | ⑥ 임베딩+rag_chunk | rag(적재↔검색) |
| [control-catalog.json](control-catalog.json) | 4.4.1(b) INTERNAL control_id 카탈로그 | 정규화·rag·mock |

## 목업 데이터 (목업우선 전략)

> 실제 스캐너·엔진을 기다리지 않고 콘솔·엔진·attackpath를 끝까지 개발하기 위한 fixture. 마지막에 실데이터로 교체. **직렬 의존(project-draft 4.3)을 두 병렬 트랙으로 분리하는 열쇠.**

| 파일 | 내용 |
|---|---|
| [mock-findings.json](mock-findings.json) | 골든 시나리오 핵심 + 잔결함 filler 20건(open/remediated/suppressed 혼합). 골든 10건은 `attack_path_id`로 묶임(attack-path 노드 전부 대응) |
| [mock-attack-paths.json](mock-attack-paths.json) | 골든 **3경로** 그래프(hero 크로스클라우드 5노드 · AWS 단독 3노드 · Azure 단독 2노드) — 4개 엣지 type 전부, `cross_cloud:true`로 AWS→Azure 횡단 |
| [mock-cases.json](mock-cases.json) | 엔진 능동조사 한 장면(UC0) — Evidence가 read-only API 4회 호출 → Reasoning 판정. "챗봇 탈출" 시연용 |

## 검증 (CI 게이트)

`python contracts/validate.py` — JSON 유효성 + 의미 정합 **7-assert(a~g)**(target-app-design §2.1) — (a)pillar (b)resource_id↔type (c)노드 grounding (d)dedup_key (e)control 존재 (f)mock-cases finding_ids·allowlist (g)**임베딩 모델 상수가 Python·TypeScript 구현 양쪽에서 계약⑥ const와 일치**(폴리글랏 드리프트 = 조용한 실패 차단). `contracts/*` 바뀌는 PR·push에서 [.github/workflows/ci.yml](../.github/workflows/ci.yml)의 `contracts 정합` 스텝이 자동 실행, 실패 시 머지 차단.
- (a) finding.pillar == catalog[control_id].pillar · (b) resource_id 2번째 세그먼트 == resource_type · (c) attack-path 노드마다 해당 path finding ≥1 · (d) dedup_key == resource_id|control_id.

## 핵심 규칙 (자주 틀리는 것)

- **`resource_id` = `{cloud}:{type}:{native_id}`** — type별 표준형은 4.4.1(a). ARN은 마지막 세그먼트만, 대소문자 보존, 계정ID·리전·path 제외.
- **`dedup_key` = `resource_id|control_id`** — 중복 제거·상태 매칭 키. 같은 리소스를 여러 스캐너가 잡으면 머지하고 `sources[]`에 누적.
- **`severity_id`는 내부 컨벤션(1=Critical~5=Info)** — 실제 OCSF(높을수록 심각)와 **반대**. 정규화 매핑 주의.
- **`control_id`는 INTERNAL-\*** (control-catalog.json) — finding과 rag_chunk가 같은 id로 조인.
- **remediated 판정은 source별 스코프**(4.4.1c) — 그 스캐너가 커버하는 control 안에서만. Trivy 배치가 S3 finding을 remediated로 만들지 않음.
- **2-pass 순서**(4.4) — 1차 규칙상관이 `attack_path_id` 부여 → 트리아지 게이트(`severity_id≤2 OR attack_path_id!=null`) → Evidence → 2차 확정.

## 졸업 상태

- [x] 계약 7종 스키마 + control-catalog(INTERNAL control 15종)
- [x] mock 데이터(findings·attack-paths·cases) — 골든 시나리오
- [x] **계약 정합 4건 수정(target-app-design §2.1)** — f5 resource_id 캐논(`secret_plaintext`), control 3종 신규(ECR-SCAN·ENTRA-SP-CRED·ENTRA-INSECURE-CFG), validate.py 4-assert + CI 게이트
- [ ] `embedding` 벡터는 mock에 미포함(1024 float) — rag 적재 시 Titan v2로 실제 생성
- [ ] ISMS-P 매핑(control-catalog `isms_p`) — RAG 코퍼스 D 작업 시 채움
- [ ] control-catalog 전체 확장 — 스캐너 연동하며 체크 추가
