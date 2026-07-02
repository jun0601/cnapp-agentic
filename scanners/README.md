# 🔍 scanners — 멀티클라우드 보안 스캐너

> AWS·Azure를 **read-only로 훑어** 보안 결함을 발견하고, 결과를 **계약⑤ ingest-envelope**으로 감싸 pipeline에 넘기는 첫 번째 관문.

👥 담당: **준형 = CSPM(cspm/) · IAM Access Analyzer** / **진우 = workload(Trivy·Inspector·kube-bench) · CIEM Entra ID**

---

## 🎯 0. 스캐너가 하는 일 한 줄

클라우드 계정을 스캔해서 "이게 잘못됐다"는 raw 데이터를 만들고, pipeline이 알아들을 수 있는 봉투(계약⑤ envelope)에 담아서 넘긴다. **스캐너는 포맷 변환을 하지 않는다** — 그건 pipeline/normalize의 일이다.

---

## 🗺️ 1. 전체 그림 — 6기둥 × 2클라우드

```
AWS                              Azure
─────────────────────────────    ────────────────────────────────
CSPM  Security Hub · Prowler     CSPM  Defender for Cloud · Prowler
CIEM  IAM Access Analyzer        CIEM  Entra ID (Prowler entra_id_*)
Vuln  Inspector · Trivy ★        Vuln  Defender Containers
KSPM  kube-bench                 (KSPM 해당 없음)
Data  Macie (S3 PII)
IaC   (Shift-Left — CI 단계)

각 스캐너
  └─ 계약⑤ ingest-envelope 생성
        └─ SQS → pipeline/normalize → 계약① finding
```

---

## 🗂️ 2. 파일 지도

```
scanners/
└── workload/               (진우 — 워크로드 취약점)
    ├── trivy.py   ★ TrivyScanner — 컨테이너 이미지 CVE 스캔 (완료 ✅)
    └── run_demo.py   데모 + 골든 정합 검증
```

> **미착수:** cspm/(준형 — Security Hub·Prowler·Macie), CIEM 스캐너(진우 — Prowler entra_id_*).  
> Inspector·kube-bench — infra apply 후 구현 예정.

---

## ▶️ 3. 실행

```bash
# 레포 루트에서
python -m scanners.workload.run_demo
```

**출력 요약:** mock Trivy JSON(3 CVE) → `TrivyScanner.scan_from_json()` → 계약⑤ envelope → `Normalizer`로 변환 → `INTERNAL-VULN-KEV-001` 매핑, resource_id 캐논 확인, pillar=vuln → 골든 정합 OK ✅

---

## 🔬 4. Trivy 워크로드 스캐너 상세 — [workload/trivy.py](workload/trivy.py)

### 실 스캔 경로 (trivy CLI 필요)

```python
scanner = TrivyScanner()
envelope = scanner.scan_image("shop/product:latest")
# → 계약⑤ ingest-envelope (raw_inline = Trivy JSON 원본)
```

내부적으로 `trivy image --format json --quiet --severity CRITICAL,HIGH,MEDIUM <image>`를 실행하고 stdout을 파싱한다. trivy 미설치 시 `TrivyScanError` 발생(설치 안내 포함).

### mock/CI 경로 (trivy CLI 없이)

```python
scanner = TrivyScanner()
envelope = scanner.scan_from_json(trivy_json_dict, image="shop/product:latest")
```

미리 받아둔 Trivy JSON 딕셔너리를 그대로 봉투화. run_demo / CI에서 end-to-end 흐름 검증에 사용.

### 봉투화 출력 (계약⑤)

```json
{
  "envelope_id": "<uuid>",
  "source": "trivy",
  "source_format": "trivy-json",
  "cloud_hint": "aws",
  "scan_batch_id": "trivy-shop-product-latest-20260702-100000",
  "ingested_at": "2026-07-02T10:00:00Z",
  "raw_inline": { ...trivy 원본... }
}
```

`scan_batch_id`에 이미지명을 포함시켜 remediated 판정 스코프(4.4.1c — 이미지별 구분)를 지원한다.

### 버그 이력

- **ArtifactName 태그 미제거**: `shop/product:latest` → `:latest`가 `resource_id`에 붙어 mock과 불일치 → `rsplit(":", 1)` 후 태그 세그먼트(`/` 없는 마지막)를 제거하도록 수정.

---

## 🔄 5. 목업 → 실배포 스왑

| 지금 (목업) | 실배포 | 위치 |
|---|---|---|
| `scan_from_json(mock_trivy_json)` | `scan_image("ECR이미지:tag")` | workload/trivy.py |
| run_demo 직접 실행 | ECR push 이벤트(EventBridge) → Lambda → `scan_image()` → SQS | infra/target |

**스캐너 로직(trivy.py)은 무변** — Lambda 핸들러에서 `TrivyScanner().scan_image(image)`를 호출하기만 하면 된다.

---

## 🔗 6. 앞뒤 컴포넌트 연결

```
[타깃 앱 / AWS 계정]  ECR 이미지 · S3 버킷 · IAM 역할 · Entra 앱 등록
        │  read-only 스캔
        ▼
[scanners/]  → 계약⑤ envelope
        │
        ▼
[pipeline/ingest/]  EventBridge → SQS (준형, infra apply 후)
        │
        ▼
[pipeline/normalize/]  → 계약① finding[]
        │
        ▼
[attackpath/] · [engine/] · [apps/console/]
```

---

## 📋 7. 스캐너 전체 현황

| 스캐너 | 기둥 | 클라우드 | 담당 | 상태 |
|---|---|---|---|---|
| Trivy (컨테이너 이미지 CVE) | vuln | AWS | 진우 | ✅ 완료 |
| Security Hub (ASFF) | cspm | AWS | 준형 | 미착수 |
| Prowler (AWS) | cspm·ciem | AWS | 준형 | 미착수 |
| Macie (S3 PII) | cspm(data) | AWS | 준형 | 미착수 |
| IAM Access Analyzer | ciem | AWS | 준형 | 미착수 |
| Prowler entra_id_* | ciem | Azure | 진우 | 미착수 (2순위) |
| Inspector | vuln | AWS | 진우 | infra apply 후 |
| kube-bench | kspm | AWS/EKS | 진우 | infra apply 후 |
| Defender for Cloud | cspm·vuln | Azure | 진우 | 데모 때만 |
