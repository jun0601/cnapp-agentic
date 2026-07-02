# 🕸️ attackpath — 크로스클라우드 공격경로 상관

> CNAPP의 6번째 기둥 = **"단일 finding은 각각 중간 위험이나, 묶으면 Critical 탈취 경로."**
> 흩어진 finding들을 규칙(R1~R5)으로 엮어 **AWS 워크로드 → Azure 신원(Entra)** 크로스클라우드
> attack-path 그래프를 생성한다. 콘솔(React Flow)이 이 그래프를 읽어 렌더한다.

👥 담당: **준형 = 그래프 데이터 모델(model/)** / **진우 = 상관 로직 R1~R5(correlation/)**
(연계 구조 — correlation이 model로 그래프를 조립한다. 형태·불변식은 model 소유, 규칙은 correlation 소유.)

---

## 🎯 0. 이 영역이 뭘 증명하려는가

개별 스캐너는 각각 "S3 공개(중간)", "IRSA 과도(중간)", "평문 시크릿(중간)"이라고만 말한다.
**CNAPP의 가치 = 이 중간 위험들이 하나의 경로로 연결될 때 Critical이 된다는 걸 보여주는 것**(독성 조합, toxic combination). 우리 골든 시나리오는 그 경로가 **클라우드 경계를 넘는다**:

```
product 취약 이미지(KEV) → order 과도 IRSA 탈취 → member 공개 S3의 PII 탈취
                                     ↓ (평문 Azure 자격증명)
                        Azure Entra 과도권한 App 장악 → 디렉터리 전체 통제권
```

이 경로를 **자동으로 발견(상관)** 하고 **그래프로 시각화**하는 게 이 영역의 목적이다.

---

## 🗺️ 1. 흐름 (2-pass, project-draft §4.4)

```
findings[] (attack_path_id 미설정)
   │
   ▼  CorrelationEngine.correlate()  ── R1~R5 규칙 발화 검사
   │
   ▼  AttackPathGraph 조립 (model)   ── 노드·엣지 + 불변식 검증(validate_graph)
   │
   ▼  2-pass backfill                ── 체인 구성 finding에 attack_path_id 역주입
   │
   ▼  계약③ dict (to_dict)           ── 콘솔 렌더 / Reasoning 내러티브 입력
```

**2-pass인 이유:** ① 1차 상관이 경로를 찾아 `attack_path_id`를 finding에 역주입 → ② 그 id가 엔진 Triage 게이트의 승급 조건(`attack_path_id!=null`)을 만족시킨다. 즉 attack-path가 "이 finding은 깊게 볼 가치가 있다"는 신호를 엔진에 넘긴다.

---

## 🗂️ 2. 파일 지도

```
attackpath/                    # 하위 폴더 = 소유자별 — project-draft §4.6
├── model/                     (준형 — 그래프 데이터 모델)
│   ├── __init__.py     공개 API 재노출(Node·Edge·AttackPathGraph·validate_graph)
│   └── graph.py     ★ 계약③ SSOT — 노드·엣지·그래프 형태 + 불변식 검증
├── correlation/               (진우 — 상관 로직)
│   └── correlation.py  ★ R1~R5 규칙 발화 + 2-pass backfill
└── run_demo.py         상관 데모 + 골든 정합 검증
```

---

## ▶️ 3. 실행

```bash
# 레포 루트에서
python -m attackpath.run_demo
```

> 윈도우 콘솔(cp949)에서도 그냥 실행 — run_demo.py가 stdout을 UTF-8로 강제.

**출력:** 상관 결과 요약(20건 → attack-path 1건) → 공격 경로 그래프(노드·엣지) → 2-pass backfill(8건 역주입) → 골든 정합 검증(5노드·4엣지·cross_cloud·backfill) → exit=0.

---

## 🧩 4. 상관 규칙 R1~R5 — [correlation/correlation.py](correlation/correlation.py)

골든 체인은 5개 규칙이 **전부** 발화해야 성립한다(하나라도 없으면 `None`):

| 규칙 | 트리거 control_id | 의미 |
|---|---|---|
| **R1** | `VULN-KEV-001` + `SG-OPEN-INGRESS-001` | KEV 취약 워크로드 + 외부 노출 SG(토폴로지 인접) |
| **R2** | `IAM-OVERPRIV-001` | 그 워크로드에 붙은 과도 IRSA 권한 |
| **R3** | `SECRET-PLAINTEXT-001` + `ENTRA-SP-CRED-001` | 평문 Azure 자격증명(AWS) + 그 SP(Azure) |
| **R4** | `S3-PUBLIC-001` + `DATA-PII-EXPOSED-001` | 공개 S3 + 동일 버킷 PII(같은 `resource_id`여야 성립) |
| **R5** | `ENTRA-OVERPRIV-APP-001` / `ENTRA-INSECURE-CFG-001` | Entra 과도권한 App Registration |

발화 시 노드 5개(AWS 3 + Azure 2) · 엣지 4개(lateral_move·data_exfil·credential_theft·identity_takeover) 생성. **체인 길이 ≥3 → severity Critical(1) 격상**(독성 조합).

> 실배포: `_first()`의 목업 "같은 컨텍스트=인접" 가정을 **파드→ENI→SG 매핑 테이블**(R1)·실제 IRSA 정책 평가(R2)로 교체.

---

## 📐 5. 그래프 데이터 모델 — [model/graph.py](model/graph.py)

계약③(`contracts/attack-path.schema.json`)의 **단일 진실 공급원**. 노드·엣지의 형태와 불변식을 코드로 고정한다.

- **`Node`**(id·cloud·resource_id·label·pillar) / **`Edge`**(from·to·type·cross_cloud·label)
- **`AttackPathGraph`** — `add_node`/`add_edge`로 조립 → `to_dict()`로 계약③ 직렬화
- **`validate_graph`** — 불변식 검사:
  - `cloud`∈{aws,azure} · `pillar`∈6기둥 · `edge.type`∈4종 (enum)
  - `node.id` 유일 · 엣지 `from`/`to`가 **실존 노드**를 가리킴
  - **`cross_cloud` 플래그 ↔ 실제 AWS↔Azure 경계 횡단 여부 일치** (렌더 강조의 근거가 데이터와 안 어긋나게)

**설계 포인트:** `finding_ids`(어떤 finding이 이 경로를 구성했나)는 backfill용 provenance라 그래프 객체엔 두되 **`to_dict()` 직렬화에선 제외** — 계약③이 `additionalProperties:false`라 출력에 넣으면 스키마 위반이기 때문. 소유 경계도 코드에 반영: **노드/엣지 형태 = model / R1~R5 규칙 = correlation.**

---

## 🔗 6. engine과의 연결 (이 그래프는 어디로 흘러가나)

attackpath의 산출물(`attack_path_id`)은 **[engine](../engine/README.md) 영역의 입력**이 된다. 즉 이 영역은 혼자 끝나는 게 아니라 엔진의 조사를 촉발하는 **방아쇠**다:

```
attackpath: R1~R5 상관 → 공격경로 발견 → finding에 attack_path_id 도장 (2-pass backfill)
                              │
                              ▼
engine ① Triage : attack_path_id != null 이면 "깊게 볼 것"으로 승급
                              │
                              ▼
engine ③ Evidence: AI가 그 경로의 위험을 read-only API로 확증
```

즉 **attackpath가 "여기 위험한 조합이 있다"고 먼저 찾아주면 → 엔진이 "그게 진짜인지" 파고드는** 협업 구조다. 2-pass backfill(§1)이 바로 이 연결의 핵심 — 1차 상관이 찍은 `attack_path_id`가 엔진 Triage 게이트의 승급 조건이 된다.

지금은 두 데모(`attackpath.run_demo` · `engine.run_demo`)가 **따로** 돌지만, 실배포에선 상관 완료 시 발행되는 `cnapp.attackpath.correlation.completed` 이벤트가 엔진 Triage를 기동시켜 이 순서가 자동으로 이어진다(project-draft §4.4).

---

## 🔄 7. 목업 → 실배포 스왑

| 지금 (목업) | 실배포 | 파일 |
|---|---|---|
| `correlate(mock_findings)` | `correlate(rds_findings)` (정규화부가 넣은 finding 조회) | correlation.py |
| `_backfill()` (dict in-place) | `RDS UPDATE ... SET attack_path_id` | correlation.py |
| R1 "같은 컨텍스트=인접" 가정 | 파드→ENI→SG 매핑으로 실제 부착 확인 | correlation.py |

→ **그래프 모델(model/)은 무변** — 형태는 데이터 소스와 독립. `correlate()` 인터페이스도 동일.

> **✅ 2026-07-02 — 스왑 코드 작성됨:** `attackpath/correlation/handler.py`(Lambda 진입점 — `cnapp.findings.batch.completed` 구독 → RDS open finding 로드 → `correlate` → `attack_paths` upsert + `findings.attack_path_id` backfill → `cnapp.attackpath.correlation.completed` 발행). 배포 = [`infra/engine`](../infra/engine/)(상관 Lambda). 위 표의 "실배포" 열이 이제 실제 코드로 존재.

---

## ✅ 8. 골든 정합 (run_demo 검증 항목)

- `attack_path_id` = `a0000000-...0001` (mock-attack-paths.json과 일치)
- 노드 5개(AWS 3 + Azure 2) · 엣지 4개
- 엣지 4종 전부 발화(lateral_move·data_exfil·credential_theft·identity_takeover)
- **cross_cloud 엣지 = credential_theft** (AWS→Azure 경계 횡단 강조)
- 2-pass backfill ≥5건 (실제 8건)

이 검증이 초록불이면 콘솔 AttackPath 화면이 렌더할 골든 그래프가 계약③대로 재현된 것.
