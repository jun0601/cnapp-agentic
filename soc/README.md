# soc/ — SOC 확장 훅 (GuardDuty 런타임 위협 탐지)

> **범위 밖(확장 훅)을 "실증"만 하는 독립 데모.** 핵심 CNAPP 파이프라인과 완전히 분리돼 있다 — 계약 스키마·RDS·control-catalog·console을 일절 건드리지 않는다.

---

## 한 줄 요약

이 프로젝트는 **CSPM(설정 포스처)** 을 골라 CNAPP로 확장했다. **SOC(실시간 위협 탐지)** 는 처음부터 "범위 밖(확장 훅만)"으로 못박아둔 영역이다(`CLAUDE.md §3`). 이 폴더는 그 확장 훅이 **실제로 작동한다**는 것만 코어와 분리된 채 증명한다 — GuardDuty가 잡은 런타임 위협을 SOC event로 수집한다.

---

## 왜 코어에 안 넣었나 (스코프 판단 · 2026-07-24)

GuardDuty를 **실제로 코어 Findings에 통합해봤다** — 그리고 되돌렸다. "될 수 있다"와 "이 프로젝트에 속한다"는 다른 질문이었다.

**실증**: AWS 공식 테스트 도메인(`guarddutyc2activityb.com`)을 EKS 파드에서 DNS 조회 → 약 4분 만에 **실 GuardDuty finding** 생성(`Backdoor:EC2/C&CActivity.B!DNS`, Severity 8.0/High, 샘플 API 아닌 100% 실 탐지). 직접 수집기·파서·신규 control까지 만들어 콘솔 Findings에 띄우는 데도 성공했다(기능적으로는 됐다).

**그런데 세 군데서 계속 어긋났고, 셋 다 같은 경계를 가리켰다:**

| # | 어긋난 지점 | 근본 원인 |
|---|---|---|
| ① | `scanners/` 에 안 맞음 | 다른 도구(Prowler·Trivy·kube-bench)는 "지금 설정이 올바른가"를 보는 **정적 스캔**인데, GuardDuty는 상시 돌며 이상행동을 잡는 **실시간 감시**다. "스캐너"가 아니다. |
| ② | pillar(6기둥)에 안 맞음 | CSPM(설정 포스처)과 GuardDuty(런타임 위협)는 축이 다르다. 6기둥 어디에도 안 맞아 신규 `threat` pillar를 스키마에 추가하려다 멈췄다. |
| ③ | Findings 모델에 안 맞음 | Findings는 "고치면 사라짐(`open`→`remediated`)" 모델인데, GuardDuty가 잡은 건 **그 순간 일어난 사건**이다. 사건은 "고쳐서 없앨" 대상이 아니다. |

→ **결론**: GuardDuty가 안 맞았던 건 버그가 아니라, 애초에 설계 경계 밖의 것을 안으로 끌어들이려 한 것이었다. 만든 코드는 전부 되돌리고, **코어와 분리된 이 독립 데모로만** 남긴다.

> **교훈**: "일단 되게 만들 수 있는가"와 "이게 이 시스템에 속하는가"는 순서가 바뀌면 안 된다. 후자를 먼저 물었으면 스키마·카탈로그를 건드리기 전에 멈췄을 것이다.

---

## CSPM(코어) vs SOC(이 폴더)

| 축 | 코어 CNAPP (6기둥) | SOC 확장 훅 (여기) |
|---|---|---|
| 질문 | 설정이 취약한가? (posture) | 지금 공격받는가? (detection) |
| 언제 | 공격 **전** (예방) | 공격 **중** (탐지) |
| 데이터 모델 | `finding` — `open`→`remediated` (고치면 사라짐) | `SocEvent` — 불변 사건 (고쳐서 없앨 대상 아님) |
| severity | `severity_id` 1~5 (내부 컨벤션) | `severity_score` 0.0~8.9 (GuardDuty 스케일) |
| 저장 | RDS `findings` (+ attack-path 상관) | 저장 없음 (수집·표시만) |

SOC event가 CNAPP finding 필드(`status`·`attack_path_id`·`control_id`·`dedup_key`)를 **일부러 갖지 않는** 것이 이 분리의 코드 증거다(`run_demo.py`의 불변식 자기검증).

---

## 구조

```
soc/
├── README.md                     # 이 문서
├── __init__.py
├── collector.py                  # GuardDutyCollector — GuardDuty finding → SocEvent
│                                 #   collect_from_json(raw)  (mock, CI 안전)
│                                 #   collect()               (real, boto3 read-only)
├── run_demo.py                   # 데모 진입점 (mock / --live)
└── fixtures/
    └── guardduty-c2-dns.json     # 실증 때 잡힌 실 finding 구조 (Backdoor:EC2/C&CActivity.B!DNS)
```

**의존성 격리**: `collector.py`는 `contracts/`·`pipeline/`·`engine/`을 import하지 않는다. `boto3`는 지연 import라 미설치/무자격 환경에서도 모듈 import는 안전하다.

---

## 실행

```bash
# mock — 계정 불필요, CI 안전 (fixtures/ 의 실 finding 구조를 변환)
python -m soc.run_demo

# live — 실 GuardDuty를 read-only로 수집 (계정·boto3 필요)
python -m soc.run_demo --live
```

`--live`는 `guardduty:ListDetectors`·`ListFindings`·`GetFindings`만 호출한다(전부 read-only, 쓰기 없음).

---

## 어떻게 확장되나 (실배포 방향)

이 데모는 "수집·표시"까지만이다. 실제 SOC로 키운다면:
- **CDR(Cloud Detection & Response)** 축으로 — GuardDuty(+VPC Flow·CloudTrail·DNS) 위협을 SIEM/타임라인으로,
- 코어 CNAPP의 posture 상관분석과는 **별개 파이프라인**으로 두어 두 축(예방·탐지)을 나란히 운영.

현업에서 **CNAPP + CDR** 결합이 트렌드인 건 맞다. 다만 "중요한 기능"과 "지금 이 프로젝트 스코프에 넣을 것"은 별개 판단이며, 이 폴더는 그 경계를 지키면서 확장 가능성만 실증한다.
