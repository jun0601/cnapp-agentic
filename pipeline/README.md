# 🔄 pipeline — 수집·정규화 파이프라인

> 스캐너가 내놓는 **제각각 포맷**(ASFF·Prowler·Trivy)을 엔진·콘솔이 공통으로 쓰는 **계약① finding** 한 가지 형식으로 바꾸는 관문.

👥 담당: **준형 = ingest(수집부)** / **진우 = normalize(정규화부)**

---

## 🎯 0. 이 파이프라인이 왜 있는가

스캐너는 3종(Security Hub ASFF / Prowler JSON / Trivy JSON)이고, 엔진·RAG·관제 앱은 하나만 안다 — **계약① OCSF-lite finding**. 이 둘 사이에서 포맷 변환·`resource_id` 정규화·중복 제거를 맡는 게 pipeline이다.

**이 파이프라인 덕분에** 스캐너를 추가하거나 바꿔도 엔진/콘솔은 코드를 손대지 않는다.

---

## 🗺️ 1. 전체 그림

```
스캐너 (raw 포맷)
   │  ASFF(Security Hub·Macie) / Prowler JSON(AWS+Azure) / Trivy JSON
   │
   ▼  ① ingest (준형)  ──────  raw를 계약⑤ envelope으로 감싸 SQS에 넣음
   │                            EventBridge → SQS → Lambda
   │
   ▼  ② normalize (진우) ────  envelope → 계약① finding[] (dedup 완료)
   │                            control-catalog 역인덱스로 control_id 매핑
   │                            resource_id 캐논화 / severity 변환
   │
   ▼  RDS(findings 테이블)  →  엔진 / RAG / 관제 앱이 읽음
```

---

## 🗂️ 2. 파일 지도

```
pipeline/
├── ingest/                  (준형 — 완료 ✅, 코드 세팅. 실배포는 infra apply 후)
│   ├── ingest.py   ★ Ingestor 클래스 — 입구 2종 → 계약⑤ 봉투 → SQS(dry-run/실)
│   └── run_demo.py    데모 실행 + 수집→정규화 핸드오프 검증
└── normalize/               (진우 — 완료 ✅)
    ├── normalizer.py   ★ Normalizer 클래스 — 포맷 파서 3종 + dedup
    └── run_demo.py       데모 실행 + 골든 정합 검증
```

---

## ▶️ 3. 실행

```bash
# 레포 루트에서
python -m pipeline.ingest.run_demo
python -m pipeline.normalize.run_demo
```

**출력 요약(ingest):** Security Hub EventBridge 이벤트(inline) + Prowler S3 드롭 이벤트(포인터) → 계약⑤ 봉투 2종 조립 → SQS 발행 dry-run → inline 봉투를 `Normalizer`에 직접 넘겨 `INTERNAL-S3-PUBLIC-001`로 정규화되는 것까지 확인(수집→정규화 핸드오프 증명) → 골든 정합 OK ✅

**출력 요약(normalize):** mock envelope 3종(ASFF·Prowler·Trivy) → finding 정규화 → control_id 7종 전부 매핑 확인 → dedup 9→8건 확인 → 골든 정합 OK ✅

---

## 🔬 4. ingest 상세 — [ingest/ingest.py](ingest/ingest.py)

### 입구 2종 (계약⑤가 이 둘을 하나의 봉투로 흡수)

| 입구 | 트리거 | 메서드 | raw 저장 방식 |
|---|---|---|---|
| ① EventBridge | Security Hub `Findings Imported` / 커스텀 `cnapp.scanner scan.completed` | `from_eventbridge(event)` | `raw_inline`(작아서 인라인) |
| ② S3 이벤트 | Prowler가 S3에 떨군 결과의 `ObjectCreated` | `from_s3_event(event)` | `raw_location`(크므로 s3 포인터) |

S3 키 경로에 `azure`가 있으면 `prowler-azure`, 없으면 `prowler-aws`로 자동 추론한다.

```python
ing = Ingestor()
envelopes = ing.from_eventbridge(securityhub_event)   # → 계약⑤ 봉투[]
ids = ing.publish(envelopes, dry_run=True)             # mock: SQS 미발행, envelope_id만 반환
```

### 실 경로

```python
ing = Ingestor(queue_url="https://sqs.ap-northeast-2.amazonaws.com/.../ingest-queue")
ing.publish(envelopes, dry_run=False)   # boto3 sqs.send_message
```

`lambda_handler(event, context)`가 실배포 진입점 — 이벤트에 `Records`가 있으면 S3, 없으면 EventBridge로 자동 판별 후 봉투화→발행까지 한 번에 처리한다.

### enum 가드

`source`/`source_format`이 계약⑤ enum을 벗어나면 봉투화 단계에서 `IngestError`로 즉시 막는다 — 정규화부가 못 알아듣는 봉투가 SQS까지 못 가게 하는 방어선.

---

## 🔬 5. normalize 상세

### ① 계약⑤ envelope 입력

```json
{
  "source": "trivy",
  "source_format": "trivy-json",
  "cloud_hint": "aws",
  "scan_batch_id": "trivy-shop-product-20260702-100000",
  "raw_inline": { ... trivy 원본 ... }
}
```

`source_format` 필드 하나로 아래 파서 중 하나를 선택한다.

### ② 파서 3종 — [normalize/normalizer.py](normalize/normalizer.py)

| `source_format` | 대상 스캐너 | 파서 함수 |
|---|---|---|
| `asff` | Security Hub · Inspector · Macie | `_parse_asff()` |
| `prowler-json` | Prowler (AWS + Azure/Entra) | `_parse_prowler()` |
| `trivy-json` | Trivy (컨테이너 이미지) | `_parse_trivy()` |
| `custom` | 이미 정규화된 finding dict | 그대로 통과 |

### ③ control_id 매핑 — control-catalog 역인덱스

```python
lookup_control("securityhub:S3.8")   # → "INTERNAL-S3-PUBLIC-001"
lookup_control("prowler:ecr_scan")    # → "INTERNAL-ECR-SCAN-DISABLED-001"
lookup_control("trivy:CVE-2024-*")    # → "INTERNAL-VULN-KEV-001"  (와일드카드)
```

`contracts/control-catalog.json`의 `sources` 배열을 역인덱스로 빌드해두고, 정확 매칭 먼저 → 와일드카드(fnmatch) 순으로 탐색. 미매핑은 `INTERNAL-UNKNOWN-001`.

### ④ resource_id 캐논화 (계약 4.4.1a 규칙)

```
ARN: arn:aws:s3:::member-pii-prod  →  aws:s3_bucket:member-pii-prod
ARN: arn:aws:iam::acct:role/my-role →  aws:iam_role:my-role
Prowler Azure: /subscriptions/.../sp-name  →  azure:service_principal:sp-name
```

형식 = `{cloud}:{type}:{native_id}` — 계정 ID·리전 제거, 마지막 경로 세그먼트만.

### ⑤ dedup (같은 리소스·control은 1건으로)

```python
dedup_key = "aws:s3_bucket:member-pii-prod|INTERNAL-S3-PUBLIC-001"
```

같은 `dedup_key`가 여러 소스(Security Hub + Prowler)에서 오면 finding은 1건으로 합치고 `sources` 배열에 양쪽을 누적. `last_seen`은 더 최신으로 갱신.

---

## 🔄 6. 목업 → 실배포 스왑

| 지금 (목업) | 실배포 | 위치 |
|---|---|---|
| `from_eventbridge()`/`from_s3_event()` 직접 호출, `publish(dry_run=True)` | EventBridge/S3가 `lambda_handler()`를 트리거, `publish(dry_run=False)` | pipeline/ingest/ |
| `run_demo.py`가 mock envelope 직접 생성 | Lambda가 SQS 메시지에서 envelope 꺼냄 | pipeline/ingest/ |
| `Normalizer().normalize(envelope)` 호출 후 콘솔 출력 | 결과 finding을 RDS에 upsert | Lambda 핸들러 |

**ingest.py·normalizer.py 로직은 무변** — 각 Lambda 핸들러에서 `Ingestor().lambda_handler(event)` / `Normalizer().normalize(envelope)`를 호출하기만 하면 실배포 전환 완료. 전제조건: `infra/shared` apply(EventBridge 룰·SQS 큐·Lambda) 완료.

---

## 🔗 7. 앞뒤 컴포넌트 연결

```
[scanners/]  scan_image() 등 → 계약⑤ envelope
                │
                ▼
[pipeline/ingest/]  from_eventbridge()/from_s3_event() → publish() → SQS (실배포: infra apply 후)
                │
                ▼
[pipeline/normalize/]  Normalizer.normalize(envelope) → finding[]
                │
                ▼
[RDS findings 테이블]
        ├── [engine/]  Triage 게이트 입력
        ├── [attackpath/]  R1~R5 상관 규칙 입력
        └── [apps/console/]  관제 앱 표시
```
