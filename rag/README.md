# 📚 rag — RAG 검색·답변 생성

> **"이 보안 결함이 왜 위험한가, 어떻게 고쳐야 하는가"**를 AI가 지식베이스를 참고해 한국어로 설명하는 컴포넌트.  
> 순수 LLM에게만 맡기면 할루시네이션·비일관성이 생기므로, **관련 보안 청크를 먼저 검색해서 LLM에 주입**(RAG)한다.

👥 담당: **준형 = corpus(코퍼스 빌드·임베딩·pgvector 적재)** / **진우 = retrieval(검색·답변 생성)**

---

## 🎯 0. 이 컴포넌트가 만드는 한 장면 (UC1)

관제 앱 Finding 상세 화면에서 사용자가 보안 항목 하나를 클릭하면:

```
【Critical 등급】 KEV-listed CVE in container image
리소스: aws:eks_pod:shop/product

KEV(Known Exploited Vulnerabilities) 목록에 등재된 CVE는 실제 공격에 이미
악용된 취약점으로, CISA가 연방기관에 패치를 의무화한 항목입니다.
컨테이너 이미지에 이런 CVE가 있으면 공격자가 즉시 악용 가능한 진입점이 됩니다.

권고 조치:
이미지를 최신 패치 버전으로 즉시 교체하고, ECR scan-on-push를 활성화해
향후 취약 이미지 배포를 차단하세요.

에이전트 조사(2회)에서 실환경 위험이 추가로 확인되었습니다.
```

이 설명을 만드는 것이 `rag/`의 역할이다.

---

## 🗺️ 1. 전체 그림

```
mock_corpus.py (진우 — control별 한국어 청크 원문, embedding 없음)
   │
   ▼  CorpusLoader.load() (준형)
   │     mock: 텍스트 해시 기반 결정적 1024-dim 벡터(dry-run)
   │     real: Titan Embed v2 임베딩 → pgvector UPSERT
   │
   ▼  계약⑥ 완성 청크 { chunk_id, text, embedding[1024], embedding_model, dim, metadata }
         (pgvector에 적재됨 — 검색부가 여기서 읽음)


finding (계약①)
   │  control_id = "INTERNAL-VULN-KEV-001"
   │
   ▼  RAGRetriever.search_by_finding()
   │     mock: control_id 직접 매핑 → mock_corpus에서 청크 반환
   │     real: 제목 → Titan Embed v2(1024-dim) → pgvector cosine 검색
   │
   ▼  청크 2~3개 (계약⑥ rag-chunk)
   │     { chunk_id, text, embedding_model, dim, metadata.control_id, ... }
   │
   ▼  RAGAnswerGenerator.generate(finding, chunks, evidence)
   │     mock: 템플릿 기반 한국어 설명 조합
   │     real: Bedrock Claude Sonnet converse API
   │             system = "지식베이스: {청크 텍스트들}"
   │             user   = finding 정보 + 에이전트 조사 결과
   │
   ▼  { explanation, rag_refs, model_trace }
         ↓ rag_refs → case.reasoning.rag_refs (계약⑦)
         ↓ explanation → 관제 앱 Finding 상세 화면
```

> **적재(corpus)와 검색(retrieval)은 반드시 같은 임베딩 모델**(`amazon.titan-embed-text-v2:0`, 1024-dim)이어야 벡터가 맞는다 — 계약⑥ `embedding_model`/`dim`이 const로 강제.

---

## 🗂️ 2. 파일 지도

```
rag/
├── corpus/               (준형 — 완료 ✅)
│   ├── loader.py    ★ CorpusLoader — 청크 → 임베딩 → pgvector 적재
│   └── run_demo.py    데모 실행 + 계약⑥ 검증 + 카탈로그 커버리지 확인
└── retrieval/            (진우 — 완료 ✅)
    ├── mock_corpus.py  ★ 14 INTERNAL control × 한국어 청크 24개
    ├── retriever.py      RAGRetriever — 청크 검색
    ├── answer_gen.py     RAGAnswerGenerator — 한국어 설명 생성
    └── run_demo.py       데모 실행 + 골든 정합 검증 (6개 체크)
```

---

## ▶️ 3. 실행

```bash
# 레포 루트에서
python -m rag.corpus.run_demo
python -m rag.retrieval.run_demo
```

**출력 요약(corpus):**
1. 진우 `mock_corpus.all_chunks()`(24개, embedding 없음) 로드
2. `CorpusLoader.load(dry_run=True)` — mock 임베딩(결정적 1024-dim)으로 계약⑥ 청크 완성
3. 계약⑥ 검증(embedding[1024]·model/dim const·metadata.control_id) 전 청크 OK
4. 같은 텍스트 → 같은 벡터(결정성) 확인
5. control-catalog(14종) 커버리지 확인 → 전체 OK ✅

**출력 요약(retrieval):**
1. mock finding 3건(KEV·S3공개·Entra과도권한) → 청크 검색 → 설명 생성
2. `search_multi` 일괄 검색 확인
3. 코퍼스 커버리지 확인 (14개 control 전부 커버)
4. 골든 정합 6개 체크 → 전부 OK ✅

---

## 🔬 4. 단계별 상세

### 📦 mock_corpus.py — 지식베이스 원천

14개 INTERNAL control마다 한국어 청크 1~2개 = 총 24개 청크.

```python
"INTERNAL-VULN-KEV-001": [
    {
        "chunk_id": "c1000000-0000-4000-8000-000000000001",
        "text": "KEV 목록에 등재된 CVE는 실제 공격에 이미 악용된 취약점으로...",
        "metadata": {
            "control_id": "INTERNAL-VULN-KEV-001",
            "cloud": "aws",
            "service": "ECR/EKS",
            "severity": 1,
            ...
        }
    },
    { "chunk_id": "...", "text": "권고 조치: 이미지를 최신 패치 버전으로..." }
]
```

**계약⑥ const 필드** (`embedding_model`, `dim`)는 getter에서 자동 주입 — 데이터 정의를 깔끔하게 유지하면서 스키마를 충족한다:

```python
_MOCK_CONST = {"embedding_model": "amazon.titan-embed-text-v2:0", "dim": 1024}

def get_chunks_by_control(control_id: str) -> list[dict]:
    return [_inject_const(c) for c in _CORPUS.get(control_id, [])]
```

> `embedding`(1024-dim float 배열)은 mock_corpus에서 의도적으로 제외 — `CorpusLoader`(아래)가 적재 시 채운다.

### 📥 CorpusLoader — [corpus/loader.py](corpus/loader.py)

`mock_corpus.py`의 청크 원문(embedding 없음)을 받아 임베딩을 채우고 pgvector에 적재하는 준형 쪽 대칭.

```python
loader = CorpusLoader(mock=True)

# 텍스트 → 1024-dim 벡터 (mock=해시 시드 결정적 벡터 / real=Titan Embed v2)
vec = loader.embed("KEV 목록에 등재된 CVE는...")

# 청크 원문(chunk_id·text·metadata) → 계약⑥ 완성 청크(embedding 채움)
chunk = loader.to_chunk(seed)

# 여러 청크 일괄 적재. dry_run=True면 DB 없이 계약⑥ 청크만 생성(mock)
result = loader.load(seed_chunks, dry_run=True)
# result = {"loaded": 24, "dim": 1024, "model": "amazon.titan-embed-text-v2:0",
#           "controls": [...14종...], "chunks": [...]}
```

real 모드(`mock=False, pg_dsn=...`): `embed()`가 Bedrock Titan Embed v2 `invoke_model`을 호출하고, `load(dry_run=False)`가 psycopg2로 `rag_chunks` 테이블에 UPSERT한다(둘 다 지연 import — mock 환경에서 boto3/psycopg2 미설치여도 무해).

`validate_chunk(chunk)`로 계약⑥ 정합(필수키·embedding 차원·model/dim const·metadata.control_id)을 검사할 수 있다 — run_demo가 적재된 전 청크에 대해 이 검증을 돌린다.

### 🔎 RAGRetriever — [retrieval/retriever.py](retrieval/retriever.py)

```python
retriever = RAGRetriever(mock=True)

# finding 하나 → 관련 청크 검색
chunks = retriever.search_by_finding(finding, top_k=2)

# 여러 finding 일괄 (control_id 중복 검색 방지)
multi = retriever.search_multi(findings, top_k_each=2)
# → {finding_id: [chunk, ...]}
```

mock 모드: `control_id` 직접 매핑. 모르는 `control_id`면 `[]` 반환.  
real 모드: `query_text` → Titan Embed v2 벡터화 → pgvector cosine similarity 검색.

### 💬 RAGAnswerGenerator — [retrieval/answer_gen.py](retrieval/answer_gen.py)

```python
generator = RAGAnswerGenerator(mock=True)
out = generator.generate(finding, chunks, evidence=evidence_list)

# out = {
#   "explanation": "【Critical 등급】 ...",
#   "rag_refs": ["c1000000-...", "c1000001-..."],
#   "model_trace": {"stage": "rag_answer", "model": "mock", "tokens": 0}
# }
```

`rag_refs`는 사용된 청크의 `chunk_id` 목록 — 이걸 `case.reasoning.rag_refs`(계약⑦)에 채운다.

`evidence`를 넘기면 에이전트 조사 결과도 설명에 반영된다:
```
에이전트 조사(2회)에서 실환경 위험이 추가로 확인되었습니다.
```

---

## 🔒 5. 계약⑥ rag-chunk 스키마 연결

```
contracts/rag-chunk.schema.json
  required: chunk_id, text, embedding_model, dim, metadata
  embedding_model: const "amazon.titan-embed-text-v2:0"
  dim: const 1024
  embedding: 1024-dim float[] (mock에서는 제외)
  metadata.control_id: control-catalog.json의 key와 동일 택소노미
```

---

## 🔄 6. 목업 → 실배포 스왑

| 지금 (목업) | 실배포 | 파일 |
|---|---|---|
| `CorpusLoader(mock=True)` — 결정적 벡터 + dry-run | `CorpusLoader(mock=False, pg_dsn=...)` — Titan Embed v2 + pgvector UPSERT | corpus/loader.py |
| `RAGRetriever(mock=True)` — control_id 직접 매핑 | `RAGRetriever(mock=False)` — Titan Embed v2 + pgvector cosine | retrieval/retriever.py |
| `RAGAnswerGenerator(mock=True)` — 템플릿 | `RAGAnswerGenerator(mock=False)` — Bedrock Claude Sonnet | retrieval/answer_gen.py |

**전제조건(실배포 전):**
1. `PG_DSN` 환경변수 — RDS pgvector DSN
2. `CorpusLoader(mock=False).load(mock_corpus.all_chunks(), dry_run=False)` 1회 실행 — Titan Embed v2로 24개 청크 벡터화 후 pgvector INSERT
3. Bedrock 모델 액세스 활성화 (서울 리전) — Sonnet inference profile ID **확정됨**: `global.anthropic.claude-sonnet-4-5-20250929-v1:0`(2026-07-03 `aws bedrock list-inference-profiles` 확인, answer_gen.py 반영). 기존 bare name은 404였음.

**적재·검색 로직(loader.py·retriever.py·answer_gen.py)은 무변** — 생성자 인자(`mock=False`)만 바꾸면 실배포 전환 완료.

---

## 🔗 7. 엔진과의 연결 (UC0 vs UC1)

| 용도 | 단위 | 연결 위치 |
|---|---|---|
| **UC1** Finding 상세 설명 | finding 1건 | 관제 앱 백엔드 → `search_by_finding()` + `generate()` |
| **UC0** case 내러티브 보강 | case 전체 | `engine/reasoning/reasoning.py` → Orchestrator 루프 중 `rag_refs` 채움 |

```
engine Orchestrator
   ├── case.finding_ids 순회
   ├── search_by_finding(f) → chunks
   ├── generate(f, chunks, evidence) → {explanation, rag_refs}
   └── case.reasoning.rag_refs = dedup(모든 rag_refs)
```
