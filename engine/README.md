# engine — 에이전틱 조사 엔진

CNAPP의 차별점("챗봇 아님 — LLM이 read-only API를 **스스로 호출**해 증거 수집"). 목업 우선으로
로직을 먼저 완성하고, 실배포 때 executor·플래너만 실물로 갈아끼운다.

담당: **준형 = Triage · Evidence** / 진우 = Hypothesis · Reasoning · Orchestrator.

## 흐름 (2-pass, project-draft §4.4)

```
findings → ① Triage 게이트(승급 소수만, 비용통제)
        → ② Evidence 능동조사(read-only 툴 자가 호출, 계약④ allowlist 강제)
        → case(계약⑦) → ③ Reasoning(진우: 내러티브·판정 리포트)
```

## 폴더

```
engine/
├── core/
│   ├── contracts.py   계약 로딩(findings·attack-path·allowlist·control 카탈로그)
│   ├── tools.py       ★read-only 툴 실행기 — allowlist 강제 + 목업 canned 응답
│   └── case.py        계약⑦ case 객체 빌더 + 스키마 정합 체크
├── triage/triage.py   트리아지 게이트(escalate = severity<=2 OR attack_path)
├── evidence/evidence.py  Evidence 에이전트(계획→툴 호출→증거→판정)
└── run_demo.py        오케스트레이션 데모 + 검증
```

## 실행

```bash
# 레포 루트에서
python -m engine.run_demo
```
출력: 트리아지 게이트(20건→승급 N건) → Evidence가 read-only 툴 4회 자가 호출 →
confirmed 판정 → case 스키마·골든 정합 검증 → `engine/out_case.json` 저장.

## 목업 → 실배포 전환 (스왑 포인트)

| 지금(목업) | 실배포 |
|---|---|
| `MockToolExecutor`(canned 응답) | `RealToolExecutor`(boto3 / MS Graph, 단일 read-only 역할) |
| 규칙 플래너 `PLAN_BY_CONTROL`(control→tool) | Bedrock LLM이 tool 선택(진짜 tool use) |
| `contracts.load_findings()`(mock JSON) | 정규화부가 RDS에 넣은 findings 조회 |

→ **Evidence/Triage 로직은 무변**(인터페이스 동일). 계약이 SSOT라 스왑이 매끄럽다.

## 거버넌스 (read-only first)

- `tools.py`가 **계약④ allowlist 밖 툴 호출을 차단**(`ToolNotAllowed`) — 변경/쓰기 API 절대 실행 안 함.
- 변경(remediation)은 엔진이 아니라 **HITL 승인 → Step Functions**(분리된 격상 역할)로만.
