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
├── cspm/                   (준형 — 설정·데이터·AWS 권한 — 완료 ✅)
│   ├── cspm.py    ★ CSPMScanner — Security Hub·Macie(ASFF) + Prowler(AWS/Azure CLI 공용) → 계약⑤ envelope
│   └── run_demo.py   데모 + 골든 정합 검증
├── workload/               (진우 — 워크로드 취약점 — 완료 ✅)
│   ├── trivy.py   ★ TrivyScanner — 컨테이너 이미지 CVE 스캔
│   └── run_demo.py   데모 + 골든 정합 검증
└── ciem/                   (진우 — 신원·권한 — 완료 ✅)
    ├── entra.py      ★ EntraCIEMScanner — Prowler entra_id_* 결과 → 계약⑤ envelope
    └── run_demo.py   데모 + 골든 정합 검증 (f8·f9·f16·f17 4종)
```

> **미착수:** Inspector·kube-bench — infra apply 후 구현 예정.

---

## ▶️ 3. 실행

```bash
# 레포 루트에서
python -m scanners.workload.run_demo
python -m scanners.ciem.run_demo
python -m scanners.cspm.run_demo
```

**출력 요약(workload):** mock Trivy JSON(3 CVE) → `TrivyScanner.scan_from_json()` → 계약⑤ envelope → `Normalizer`로 변환 → `INTERNAL-VULN-KEV-001` 매핑, resource_id 캐논 확인, pillar=vuln → 골든 정합 OK ✅

**출력 요약(ciem):** mock Prowler Azure 체크 4건(과도권한 App·위험 consent·SP 무만료 cred·설정 미스컨피그) → `EntraCIEMScanner.scan_from_json()` → 계약⑤ envelope → `Normalizer`로 변환 → 4개 INTERNAL-ENTRA-* control_id 매핑, golden f8·f9·f16·f17과 resource_id/severity/pillar 일치 → 골든 정합 OK ✅

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

## 🔬 5. Entra CIEM 스캐너 상세 — [ciem/entra.py](ciem/entra.py)

### mock/CI 경로 (Prowler CLI 없이)

```python
scanner = EntraCIEMScanner()
envelope = scanner.scan_from_json(prowler_azure_check_dict)  # 체크 1건 = 봉투 1개
```

Trivy·CSPM과 동일하게 "봉투화까지만" — envelope→finding 변환은 `Normalizer`(정규화부) 몫.

### 실 스캔 경로 (prowler CLI + Azure 인증 필요)

```python
scanner = EntraCIEMScanner()
envelopes = scanner.scan_prowler(checks="entra_id_*")
```

subprocess 실행 로직은 `scanners/cspm/cspm.py`의 `CSPMScanner.scan_prowler(provider="azure", ...)`를 그대로 재사용(중복 방지) — `EntraCIEMScanner.scan_prowler()`는 CIEM 도메인에 맞는 진입점만 노출하는 얇은 래퍼다. 인증은 manual-infra §3.6.3 Prowler SP(GitHub Federated Credential, 키리스).

### 봉투화 출력 (계약⑤)

```json
{
  "envelope_id": "<uuid>",
  "source": "prowler-azure",
  "source_format": "prowler-json",
  "cloud_hint": "azure",
  "scan_batch_id": "prowler-azure-entra-20260702-100000",
  "ingested_at": "2026-07-02T10:00:00Z",
  "raw_inline": { "checkID": "entra_id_sp_credential_no_expiry", "service": "entraid", "resourceId": "azure:service_principal:...", ... }
}
```

`resourceId`는 캐논 형식(`azure:type:native_id`)을 스캐너 단계에서 그대로 전달(passthrough) — Prowler Azure 출력엔 AWS ARN 같은 정규화 대상이 없어 `Normalizer._canon_resource_id`가 그대로 통과시킨다(4.4.1a).

### 커버하는 control (계약 control-catalog.json)

| checkID (예) | control_id | pillar |
|---|---|---|
| `entra_id_app_registration_overprivileged` | `INTERNAL-ENTRA-OVERPRIV-APP-001` | ciem |
| `entra_id_admin_consent_unverified_app` | `INTERNAL-ENTRA-RISKY-CONSENT-001` | ciem |
| `entra_id_sp_credential_no_expiry` | `INTERNAL-ENTRA-SP-CRED-001` | ciem |
| `entra_id_app_redirect_uri_insecure` | `INTERNAL-ENTRA-INSECURE-CFG-001` | cspm (Defender secure-score 축) |

---

## 🔄 6. 목업 → 실배포 스왑

| 지금 (목업) | 실배포 | 위치 |
|---|---|---|
| `scan_from_json(mock_trivy_json)` | `scan_image("ECR이미지:tag")` | workload/trivy.py |
| `scan_from_json(mock_prowler_check)` | `scan_prowler(checks="entra_id_*")` | ciem/entra.py |
| run_demo 직접 실행 | ECR push 이벤트(EventBridge) → Lambda → `scan_image()` → SQS | infra/target |
| run_demo 직접 실행 | GitHub Actions cron(Prowler SP OIDC) → `scan_prowler()` → SQS | manual-infra §3.6.3 |

**스캐너 로직(trivy.py·entra.py)은 무변** — Lambda/cron 핸들러에서 각 스캐너 클래스를 호출하기만 하면 된다.

---

## 🔗 7. 앞뒤 컴포넌트 연결

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

## 📋 8. 스캐너 전체 현황

| 스캐너 | 기둥 | 클라우드 | 담당 | 상태 |
|---|---|---|---|---|
| Trivy (컨테이너 이미지 CVE) | vuln | AWS | 진우 | ✅ 완료 |
| Security Hub (ASFF) | cspm | AWS | 준형 | ✅ 완료(`scan_securityhub`) |
| Prowler (AWS) | cspm·ciem | AWS | 준형 | ✅ 완료(`scan_prowler(provider="aws")`) |
| Macie (S3 PII) | cspm(data) | AWS | 준형 | ✅ 완료(Security Hub ASFF 경유) |
| IAM Access Analyzer | ciem | AWS | 준형 | Prowler AWS 체크로 커버(별도 API 미구현) |
| Prowler entra_id_* | ciem | Azure | 진우 | ✅ 완료(`scanners/ciem/`) |
| Inspector | vuln | AWS | 진우 | infra apply 후 |
| kube-bench | kspm | AWS/EKS | 진우 | infra apply 후 |
| Defender for Cloud | cspm·vuln | Azure | 진우 | 데모 때만 |
