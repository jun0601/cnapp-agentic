# engine — 에이전틱 조사 엔진

> CNAPP의 차별점 = **"챗봇 아님 — LLM이 read-only API를 스스로 호출(tool use)해 증거를 수집한다."**
> 목업 우선으로 로직을 먼저 완성하고, 실배포 때 executor·플래너만 실물로 갈아끼운다.

담당: **준형 = Triage · Evidence** / **진우 = Hypothesis · Reasoning · Orchestrator**
(단순 반반 아님 — 앞 단계가 채운 `case` 객체를 뒷 단계가 이어받는 **연계** 구조.)

---

## 0. 이 엔진이 뭘 증명하려는가 (제일 중요)

심사자의 질문: **"그거 그냥 ChatGPT 붙인 챗봇 아니야?"**
우리 답: **아니오. 에이전트가 스스로 read-only API를 호출해 증거를 모은다.**

사람이 "이 버킷 정책 확인해줘"라고 하나하나 시키는 게 아니라, **에이전트가 "이 위험을 확인하려면 어떤 API를 불러야 하나"를 스스로 정하고 호출**한다. 이게 **"챗봇 탈출"의 단일 기준**이다. 아래 실행 출력의 **③ Evidence** 블록(툴 4회 호출)이 그 물리적 증거이며, **그 한 장면을 만드는 것이 엔진 전체의 목적**이다(§5 시간 컷 사수 1순위).

---

## 1. 전체 그림 — 5단계 파이프라인 (2-pass, project-draft §4.4)

```
mock-findings.json (20건)
   │
   ▼  ① Triage 게이트  ────────  20건 → 12건만 승급 (비용 통제)
   │
   ▼  ② Hypothesis    ────────  승급 건마다 "가설" 자동 생성
   │
   ▼  ③ Evidence  ★심장  ─────  가설 확인하려 read-only 툴 스스로 호출 (4회)
   │
   ▼  ④ Reasoning     ────────  증거 → 한국어 내러티브 + CRITICAL + 권고
   │
   ▼  ⑤ 검증          ────────  case 스키마·골든 정합 OK
```

**담당:** ①③ = 준형 / ②④ + 전체 조립 = 진우. 각 단계가 `case`(계약⑦) 객체를 차례로 채운다.

---

## 2. 파일 지도

```
engine/                        # 하위 폴더 = 소유자별(공유는 core 예외) — project-draft §4.6
├── core/                      (공유·예외)
│   ├── contracts.py    contracts/*.json 읽어서 엔진에 공급(단일 진실 공급원)
│   ├── tools.py     ★ read-only 툴 실행기 + allowlist 강제 (거버넌스 핵심)
│   └── case.py         계약⑦ 핸드오프 객체 빌더 + 스키마 정합 체크
├── evidence/                  (준형: Triage·Evidence)
│   ├── triage.py       ① 트리아지 게이트
│   └── evidence.py  ★ ③ 능동조사 (심장 — tool use)
├── reasoning/                 (진우: Hypothesis·Reasoning·Orchestrator)
│   ├── hypothesis.py   ② 가설 자동 생성
│   ├── reasoning.py    ④ 내러티브·위험수준·권고
│   └── orchestrator.py 전체 루프 조립 (단일 진입점)
└── run_demo.py         데모 실행 + 골든 정합 검증
```

---

## 3. 실행

```bash
# 레포 루트에서
python -m engine.run_demo
```

> 윈도우 콘솔(cp949)에서도 그냥 실행하면 된다 — run_demo.py가 stdout을 UTF-8로 강제한다(한글·기호 UnicodeEncodeError 방지).

**출력 요약:** 트리아지(20→12 승급) → Hypothesis 가설 목록 → **Evidence가 read-only 툴 4회 자가 호출** → Reasoning CRITICAL 내러티브 → case 스키마·골든 정합 검증 → `engine/out_case.json` 저장.

---

## 4. 단계별 상세 (출력 ↔ 코드)

### ① Triage 게이트 — [evidence/triage.py](evidence/triage.py)

```python
escalate = status == "open" and (sev <= 2 or on_path)
```

**왜 있나 = 비용.** finding이 1000건이면 전부 LLM 풀 조사 시 Bedrock 요금 폭발. 게이트로 **"High/Critical(severity≤2) 이거나 공격경로 소속(attack_path_id 있음)"**만 승급하고, 나머지는 값싼 설명(UC1)에서 멈춘다. 20건 중 12건 통과. 이 "무엇을 깊게 볼지" 판단 자체가 에이전트의 첫 지능.

### ② Hypothesis — [reasoning/hypothesis.py](reasoning/hypothesis.py)

승급된 finding마다 **"이게 진짜면 이런 위험이다"라는 검증 가능한 가설**을 만든다. 지금은 `control_id → 템플릿` 규칙(`_HYPOTHESIS_BY_CONTROL`). attack-path에 `cross_cloud` 엣지가 있으면 **크로스클라우드 체인 가설**(AWS 침해 → 평문 Azure SP → Entra 장악)을 추가 — 골든 시나리오 핵심. 이 가설이 ③ Evidence가 "뭘 확인할지"의 근거가 된다.

### ③ Evidence — ★ 심장 — [evidence/evidence.py](evidence/evidence.py)

**(a) 계획 — "어떤 툴을 부를까"를 스스로 정함**
```python
PLAN_BY_CONTROL = {
  "INTERNAL-S3-PUBLIC-001":        ["s3:GetBucketPolicy", "s3:GetPublicAccessBlock"],
  "INTERNAL-DATA-PII-EXPOSED-001": ["macie2:GetFindings"],
  "INTERNAL-IAM-OVERPRIV-001":     ["iam:SimulatePrincipalPolicy"],
}
```
finding의 `control_id` → 확인에 필요한 read-only 툴 매핑. **실배포에선 이 규칙 플래너가 Bedrock LLM으로 교체**(LLM이 finding 읽고 스스로 툴 선택 = 진짜 tool use). 지금은 규칙이라 결정적 → 데모 재현성.

**(b) 실행 — 스스로 호출**
```python
for tool, resource_id in plan:
    results.append(self.executor.execute(tool, resource_id))  # ★ 에이전트가 스스로 호출
```
이 루프가 **"챗봇 탈출"의 물리적 실체**. 사람이 안 시켜도 에이전트가 API를 부른다. 4개 결과 중 위험을 뒷받침(`confirms=True`)하는 비율 → 100% → `confirmed` 판정.

### ④ Reasoning — [reasoning/reasoning.py](reasoning/reasoning.py)

verdict(`confirmed`) + confidence(1.0) → `_risk_level` → **CRITICAL**. 증거를 사람이 읽는 한국어 내러티브로 엮고, `control_id`별 권고(S3 차단·IRSA 최소화 등)를 낸다. 실배포선 내러티브 생성이 Sonnet LLM으로 교체.

### ⑤ 검증 — [run_demo.py](run_demo.py)

`case`가 계약⑦ 스키마에 맞나 + **골든 정합**(툴 4회·confirmed·stage=reasoning) assert. 초록불이면 "심장 장면"이 의도대로 재현된 것.

---

## 5. 거버넌스 — read-only first (allowlist 강제)

[core/tools.py](core/tools.py) — 모든 툴 호출 전 검사:
```python
def _check(self, tool):
    if tool not in self.allowlist:      # 계약④ evidence-allowlist.json
        raise ToolNotAllowed(...)        # 변경/쓰기 API면 여기서 차단
```
**에이전트는 read-only만.** `s3:DeleteBucket` 등을 부르려 하면 실행기가 막는다. 변경(remediation)은 엔진이 직접 안 하고 **HITL 승인 → Step Functions** 별도 격상 경로로만. "AI가 멋대로 인프라를 바꾸는 것 아니냐"를 구조로 차단.

---

## 6. 목업 → 실배포 스왑 (딱 두 군데)

전부 목업이지만 실AWS 전환 시 바꾸는 건 2곳뿐, 나머지 로직은 무변:

| 지금 (목업) | 실배포 | 파일 |
|---|---|---|
| `MockToolExecutor` (canned 응답) | `RealToolExecutor` (boto3 / MS Graph, 단일 read-only 역할) | core/tools.py |
| `PLAN_BY_CONTROL` 규칙 플래너 | Bedrock LLM이 tool 선택 | evidence/evidence.py |
| `contracts.load_findings()` (mock JSON) | 정규화부가 RDS에 넣은 findings 조회 | core/contracts.py |

계약(`contracts/*.json`)이 SSOT라 `Orchestrator(RealToolExecutor())` 한 줄이면 실AWS로 스왑. **이 매끄러운 스왑이 목업 우선 전략의 배당금.**

---

## 7. 직접 실험해볼 거리 (이해 확인용)

1. **게이트 체감:** `evidence/triage.py`의 `sev <= 2` → `sev <= 1`로 바꿔 돌리면 escalate 수가 준다 → 게이트가 실제로 거른다는 걸 눈으로.
2. **allowlist 체감:** `contracts/evidence-allowlist.json`에서 `s3:GetBucketPolicy`를 지우고 돌리면 → `ToolNotAllowed` 크래시. 차단이 진짜라는 증거.
3. **저장물 확인:** 실행 후 `engine/out_case.json` = 에이전트가 만든 `case` 객체 전체(계약⑦ 형태). 관제 앱 FindingDetail의 Evidence 탭이 읽을 데이터.
