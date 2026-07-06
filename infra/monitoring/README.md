# infra/monitoring — 운영 관측 (진우 담당)

> CLAUDE §5 "모니터링·관제·추적(Grafana·CloudTrail)" 코드화. **shared·pipeline·console·engine 다음** 레이어(전부 remote_state로 참조만, 아무것도 안 만듦).
> 보안 findings 대시보드(관제 "앱", 준형)와는 다른 것 — 이건 "우리 플랫폼이 잘 돌고 있나"를 보는 운영 관측이다.

---

## 0. 두 가지 "관제" 구분 (헷갈리지 말 것)

| | 관제 **앱** (`apps/console`, 준형) | 운영 **관측** (`infra/monitoring`, 이 폴더, 진우) |
|---|---|---|
| 보는 것 | 보안 findings·attack-path·case | 플랫폼 자체의 헬스(가동·지연·에러·비용) |
| 사용자 | 보안 담당자(viewer/approver) | 우리 둘(운영자) |
| 데이터 소스 | RDS(findings 등) | Prometheus + CloudWatch |

---

## 1. 설계 원칙 — 왜 하이브리드인가

플랫폼이 **EKS 안**(타깃 앱 파드)과 **EKS 밖**(Lambda·RDS·SQS·ALB·Step Functions·S3·**Bedrock**)에 걸쳐 있어서, 관측도 두 세계를 하나로 묶어야 한다.

- **EKS 안** → **Prometheus**(`gitops/`에 배포될 kube-prometheus-stack: node-exporter·kube-state-metrics·cAdvisor). K8s API·파드 네트워크만 쓰고 AWS API를 안 부르므로 이 레이어(IRSA)가 필요 없음.
- **EKS 밖** → **CloudWatch**(각 서비스가 기본 제공하는 네이티브 지표, 추가 계측 없이 대부분 확보).
- **통합** → **Grafana**가 Prometheus를 기본 데이터소스로, **이 레이어가 만드는 IRSA 역할로 CloudWatch를 추가 데이터소스로** 붙여 한 화면에서 본다.

이 원칙 위에서 관측 대상을 **3개 축**으로 나눈다 — 이 프레임 자체가 맞고, 축마다 난이도·소스가 다르다.

| 축 | 무엇 | 소스 | 난이도 |
|---|---|---|---|
| ① 애플리케이션 | 타깃 앱 파드 + 관제 앱(백엔드·프론트) | Prometheus(파드) + CloudWatch(Lambda·CloudFront) | 낮음 — 표준 지표만 |
| ② 인프라 전체 | EKS·RDS·SQS·ALB·Step Functions·S3 | CloudWatch(전부 네이티브 지표) | 낮음 — 표준 지표만 |
| ③ AI(에이전트) | Bedrock 호출·에이전트 행동 | CloudWatch(Bedrock 네이티브) + **커스텀 EMF 메트릭**(직접 계측) | 중간 — 계측 코드 필요, 가장 차별화된 축 |

---

## 2. 관측 대상 카탈로그

### ① 애플리케이션

| 대상 | 지표 | 소스 | 상태 |
|---|---|---|---|
| 타깃 앱 파드(product·order·member) | 재시작 횟수·CPU/메모리·HPA 스케일링 이벤트 | Prometheus | ⬜ `gitops/monitoring`(다른 폴더) 없이는 수집 불가 — infra/monitoring 밖 |
| 관제 앱 백엔드(console-backend Lambda) | Invocations·Errors·Duration·Throttles | CloudWatch | ✅ 대시보드에 있음 |
| 관제 앱 프론트(CloudFront) | 캐시 히트율·4xx/5xx | CloudWatch | ✅ 완료(2026-07-03) — `infra/console`이 `cloudfront_distribution_id` output 추가(준형)해서 게이트 해제, 상시 위젯 |
| 로그인(Cognito) | SignIn 성공/실패율 | CloudWatch | ✅ 완료(2026-07-03, 성공 지표만 — 기본 User Pool엔 실패 카운터 없음) |

### ② 인프라 전체

| 대상 | 지표 | 소스 | 상태 |
|---|---|---|---|
| EKS 노드/클러스터 | 노드 CPU/메모리, Karpenter 프로비저닝 이벤트 | Prometheus | ⬜ `gitops/monitoring`(다른 폴더) 없이는 수집 불가 — infra/monitoring 밖 |
| RDS(pgvector) | CPUUtilization·DatabaseConnections | CloudWatch | ✅ 있음 |
| RDS(pgvector) | FreeStorageSpace·ReadIOPS | CloudWatch | ✅ 완료(2026-07-03) |
| SQS(ingest·DLQ) | 큐 깊이·DLQ 적재 | CloudWatch | ✅ 있음 |
| SQS(ingest) | ApproximateAgeOfOldestMessage(백로그 나이) | CloudWatch | ✅ 완료(2026-07-03) |
| ALB | RequestCount·TargetResponseTime·5xx | CloudWatch | ✅ 있음 |
| Lambda(ingest·normalize·correlation·orchestrator·console-backend·remediation) | Invocations·Errors·Duration·Throttles | CloudWatch | ✅ 완료(2026-07-03, 6종 전체) |
| **Step Functions(remediation HITL)** | ExecutionsSucceeded/Failed/Aborted·ExecutionTime | CloudWatch(`AWS/States`) | ✅ 완료(2026-07-03) |
| **S3 감사 버킷(Object Lock)** | NumberOfObjects·BucketSizeBytes | CloudWatch(`AWS/S3`, 일 단위) | ✅ 완료(2026-07-03) |

### ③ AI(에이전트) — 신규 설계, 가장 차별화된 축

지금 코드 기준: **Evidence 단계(`engine/evidence/bedrock_planner.py`)만 실제 Bedrock 호출**(Haiku, `global.anthropic.claude-haiku-4-5-20251001-v1:0`, Phase1에서 실증 완료). Reasoning·Hypothesis(`engine/reasoning/`)와 RAG 답변 생성(`rag/retrieval/answer_gen.py`, Sonnet 예정)은 아직 템플릿/mock — 실전환되면 모델이 2종(Haiku+Sonnet)으로 늘어나므로, **처음부터 `ModelId` 디멘션으로 설계**해야 나중에 위젯을 안 갈아엎는다.

| 레이어 | 지표 | 소스 | 계측 필요? | 위젯 상태 |
|---|---|---|---|---|
| Bedrock 호출(모델별) | Invocations·InvocationLatency·InvocationClientErrors/ServerErrors·InputTokenCount/OutputTokenCount | CloudWatch(`AWS/Bedrock`, 자동 발행) | 아니오 — 코드 변경 없이 바로 대시보드화 가능 | ✅ 완료(2026-07-03) |
| case당 추정 비용 | 위 InputTokenCount/OutputTokenCount에 단가를 곱하는 **metric math**(단가는 변수화) | CloudWatch(파생 위젯, `AWS/Bedrock` 그대로 사용) | 아니오 — 새 지표 만들 필요 없이 기존 native 지표로 계산 | ✅ 완료(2026-07-03) |
| 에이전트 행동(tool-use 횟수·확신도) | case당 tool_calls_count·confidence_score | EMF 커스텀 메트릭 | **완료(2026-07-03)** — `engine/reasoning/orchestrator.py`의 `run()`에 `_emit_case_metrics` 추가됨 | ✅ 위젯·계측 둘 다 완료(Lambda apply 후 실데이터 유입) |
| 트리아지 게이트 | FindingsEvaluated / FindingsEscalated(카운터 2개, 비율은 대시보드에서 계산) | EMF 커스텀 메트릭 | **완료(2026-07-03)** — 동일 파일 | ✅ 위젯·알람·계측 전부 완료 |
| 판정 분포·위험도 | Verdict(confirmed/inconclusive)·RiskLevel(CRITICAL 등) 디멘션별 카운트 | EMF 커스텀 메트릭 | **완료(2026-07-03)** — 동일 파일(`case["evidence_meta"]["verdict"]`·`case["reasoning"]["risk_level"]`) | ✅ 위젯·계측 완료 |
| 판정까지 걸린 시간 | TimeToVerdictMs | EMF 커스텀 메트릭 | **완료(2026-07-03)** — `run()` 시작 `t0=time.time()` + return 직전 계측 | ✅ 위젯·계측 완료 |
| **케이스별 Bedrock 토큰(=비용 귀속)** | `BedrockInputTokens`/`BedrockOutputTokens`(케이스 1건 전체 합, Converse 응답 `usage` 누적) | EMF 커스텀 메트릭 | **완료(2026-07-03, §15)** — `engine/evidence/bedrock_planner.py`(usage 캡처) → `EvidenceOutput` → `orchestrator.py` | ✅ 위젯·계측 완료. 위 "case당 추정 비용"(계정 전체 native 지표)과 달리 **트리아지를 통과해 실제로 조사한 케이스만의 토큰** — 정확한 건별 값은 CloudWatch Logs Insights로 `CaseId` 검색(§15.3) |
| **read-only tool별 호출 횟수** | `ToolInvocations`(Dimension=`Tool`) | EMF 커스텀 메트릭 | **완료(2026-07-03, §15)** — `orchestrator.py`의 `_emit_tool_usage_metrics`, `EvidenceOutput.plan`(기존 필드, 신규 캡처 불요) 집계 | ✅ 위젯(SEARCH 기반 Tool별 분포)·계측 완료 |
| (보너스) 판단 근거 리플레이 | 프롬프트·응답 전문 | Bedrock model invocation logging → S3 | 아니오(AWS 기능 on/off만) — **상시 X, 데모 캡처 구간만** | ⬜ 미착수(보너스) |
| (보너스) 분산 트레이싱 | ingest→normalize→correlation→orchestrator 요청 1건의 전체 경로 | AWS X-Ray | 각 Lambda에 X-Ray SDK 계측 필요(선택) | ⬜ 미착수(보너스) |

> EMF(Embedded Metric Format)는 Lambda가 이미 찍는 CloudWatch Logs에 특정 JSON 형식 한 줄만 추가하면 CloudWatch가 알아서 커스텀 메트릭으로 파싱한다 — 별도 서비스·의존성·비용 없음(`print(json.dumps(...))` 한 줄). **핵심 발견: case-level 지표는 전부 `Orchestrator.run()`(진우 소유, `engine/reasoning/orchestrator.py`) 안에서 뽑아낼 수 있다** — 이 메서드가 `findings`·`escalated`·완성된 `case`(evidence_meta·reasoning 포함)를 전부 쥐고 있는 유일한 지점이라, 이전 정리에서 "engine/core 조율 필요"라고 했던 건 정정 — **`engine/core`·`engine/evidence`(준형 파일)는 한 줄도 안 건드려도 된다.** 유일하게 준형 파일을 만져야 하는 경우는 "모델별 실제 토큰 사용량을 case 안에 남기고 싶을 때"뿐인데, 그건 위처럼 Bedrock native 지표로 대체 가능해서 필요 없음.

#### 3.1 계측 — `engine/reasoning/orchestrator.py`에 구현 완료(2026-07-03)

당초 스켈레톤에서 **한 가지 수정** 후 실제 반영됨: `Dimensions`를 `[["Verdict","RiskLevel"]]` 하나가 아니라 **`[[], ["Verdict","RiskLevel"]]`(빈 세트 포함 2개)로 발행**한다. 이유 — CloudWatch **알람은 metric math에서 `SEARCH()`를 지원하지 않는다**(동적 시계열 개수라 단일 임계값과 안 맞음). Dimensions가 `["Verdict","RiskLevel"]`뿐이면 무디멘션 "총계" 시계열이 없어서, 총계를 보려면 대시보드에서만 되는 `SEARCH()+SUM()`에 의존해야 하고 **알람(§4의 트리아지 게이트 알람)에서는 그 총계를 아예 조회할 방법이 없다.** 빈 세트를 함께 선언하면 한 번의 `print(json.dumps(...))`로 ① 무디멘션 총계 시계열(대시보드 총계 위젯·알람이 SEARCH 없이 직접 참조) ② Verdict×RiskLevel 세부분해 시계열(대시보드 분포 위젯만 SEARCH로 펼침)을 **동시에** 얻는다 — 이게 EMF의 표준 기능이라 추가 코드·비용 없음.

```python
import json, os, time

def _emit_case_metrics(case: dict, findings_n: int, escalated_n: int, elapsed_ms: float) -> None:
    # Lambda 안에서만 발행(로컬 run_demo/run_e2e 콘솔 스팸 방지)
    if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return
    meta = case.get("evidence_meta", {})
    reasoning = case.get("reasoning", {})
    emf = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": "CnappAgentic/Engine",
                "Dimensions": [[], ["Verdict", "RiskLevel"]],  # 빈 세트 = 무디멘션 총계(알람용)
                "Metrics": [
                    {"Name": "FindingsEvaluated", "Unit": "Count"},
                    {"Name": "FindingsEscalated", "Unit": "Count"},
                    {"Name": "ToolCallsPerCase", "Unit": "Count"},
                    {"Name": "ConfidenceScore", "Unit": "None"},
                    {"Name": "TimeToVerdictMs", "Unit": "Milliseconds"},
                ],
            }],
        },
        "Verdict": meta.get("verdict", "unknown"),
        "RiskLevel": reasoning.get("risk_level", "unknown"),
        "CaseId": case.get("case_id"),
        "FindingsEvaluated": findings_n,
        "FindingsEscalated": escalated_n,
        "ToolCallsPerCase": meta.get("tool_calls_count", 0),
        "ConfidenceScore": meta.get("confidence_score", 0.0),
        "TimeToVerdictMs": elapsed_ms,
    }
    print(json.dumps(emf))
```

`run()` 맨 앞에 `t0 = time.time()`, `return` 직전에 `_emit_case_metrics(c, len(findings), len(escalated), (time.time()-t0)*1000)` — 실제로 이렇게 두 줄만 추가됨(`engine/reasoning/orchestrator.py`). 새 pip 의존성·Lambda 레이어 변경 없음(EMF는 stdout 규약일 뿐). `run_demo`·`run_e2e` 무회귀 확인(Lambda 밖이라 미발행).

> **2026-07-03 갱신**: `_emit_case_metrics`에 `BedrockInputTokens`/`BedrockOutputTokens` 파라미터가 추가되고, 케이스마다 tool-use 내역을 별도 EMF 라인으로 찍는 `_emit_tool_usage_metrics`가 새로 생겼다 — 위 코드 스니펫은 최초 구현 시점 스냅샷이라 최신 버전은 §15 참고.

#### 3.2 비용 위젯 (metric math, 코드 계측 없이 대시보드에서만)

Bedrock native `InputTokenCount`·`OutputTokenCount`(모델별)에 단가를 곱하는 CloudWatch metric math 식 — 예: `(m_in/1000)*u_in_price + (m_out/1000)*u_out_price`. 단가는 하드코딩하지 말고 `variables.tf`에 `bedrock_haiku_price_in/out`·`bedrock_sonnet_price_in/out` 변수로 빼서, 가격이 바뀌면 대시보드가 아니라 변수만 갱신. (2026-07 기준 시세 대략 Haiku $1/$5, Sonnet $3~10/M 토큰대 — **apply 시점에 AWS Bedrock 가격 페이지에서 재확인 필수**, 리전별·크로스리전 추론 시 +10% 프리미엄 붙을 수 있음.)

---

## 3. 무엇을 만드나 (이 레이어의 테라폼 리소스)

| 리소스 | 용도 | 상태 |
|---|---|---|
| `aws_iam_role.grafana` + policy | Grafana ServiceAccount(IRSA) → CloudWatch/Logs read-only | ✅ 있음 |
| `aws_cloudwatch_dashboard.platform` | ①②③ 전 축 시각화(**24개** 위젯 — Lambda 6·인프라 8·Bedrock 2·비용 1·엔진 EMF 6·CloudFront 1, §14·§15 재검산) | ✅ 완료(2026-07-03) |
| Bedrock 지표 위젯(모델별) + 비용 metric math | 축③ 1단 | ✅ 완료(2026-07-03) |
| EMF 커스텀 메트릭 위젯 6종(4종 무디멘션 총계·1종 SEARCH 기반 판정분포·1종 SEARCH 기반 tool분포) | 축③ 2단 | ✅ 위젯·계측 둘 다 완료(§13·§15) |
| Step Functions·감사 S3·remediation Lambda 위젯 | ②의 누락 3종 | ✅ 완료(2026-07-03) |
| CloudTrail→CWLogs 배관(로그그룹·IAM 역할) | §10 | ✅ 완료(2026-07-03) |
| Teams 알림(SNS·Lambda·시크릿·알람 7종 — Bedrock 비용 가드레일 포함) | §11·§15 | ✅ 완료(2026-07-03) |

---

## 4. gitops 연동 — 파일 추가가 "불가피"한가

**기술적으로 강제는 아니다.** `helm install kube-prometheus-stack ...`을 ArgoCD 없이 수동으로 실행해도 Prometheus/Grafana 자체는 뜬다. 하지만:

- 이 프로젝트는 이미 **"K8s에 올라가는 건 전부 GitOps(ArgoCD pull-sync)"** 원칙을 `gitops/argocd/app-target.yaml`(타깃 앱)·`gitops/autoscaling/hpa.yaml`(파드층 HPA)로 확립해 놓았다(노드층 Karpenter는 IAM과 한 몸이라 예외적으로 `infra/karpenter` terraform 소유 — 2026-07-03 분리). 모니터링만 예외로 수동 설치하면 self-heal·드리프트 교정 스토리(project-draft §19)가 이 레이어만 깨지고, 포폴 일관성도 떨어진다.
- 지금 `infra/monitoring/variables.tf`·`main.tf` 주석이 이미 `gitops/monitoring/values.yaml`의 존재를 전제로 Grafana SA 이름(`kube-prometheus-stack-grafana`)·네임스페이스(`monitoring`)를 하드코딩해놨다 — 즉 **설계가 이미 gitops 경로를 전제로 되어 있어서**, 지금 와서 수동 설치로 바꾸면 이 레이어의 IRSA 코드도 다시 손봐야 한다.

**결론: 기술적 필수는 아니지만, 지금 설계·프로젝트 원칙을 유지하려면 사실상 추가하는 게 맞다.** 최소 2개 파일 제안(기존 `gitops/argocd/app-target.yaml` 패턴과 동일):

```
gitops/
├── argocd/
│   └── app-monitoring.yaml        # ArgoCD Application — kube-prometheus-stack Helm 차트 참조
└── monitoring/
    └── kube-prometheus-stack-values.yaml   # Grafana SA annotation(이 레이어의 IRSA ARN 출력값 주입)
```

대안(비권장)을 원하면: gitops 건드리지 않고 `helm install`로 수동 배포 — 더 빠르지만 self-heal 없음, 드리프트 나면 수동 복구, "GitOps 전부" 서사에서 이 레이어만 예외가 됨. 시간이 정말 없을 때만 임시로.

---

## 5. 의존 · apply 순서

```
0. infra/shared (EKS OIDC)
1. infra/backend · infra/console  (Lambda·SQS·ALB·Step Functions·S3 감사버킷 확정)
2. gitops: ArgoCD 설치 → kube-prometheus-stack(app-monitoring.yaml) → Prometheus/Grafana 기동
3. infra/monitoring apply → grafana_irsa_role_arn 출력
4. gitops/monitoring/kube-prometheus-stack-values.yaml의 SA annotation에 3번 출력값 채워 재적용
5. 테스트/확인 후 destroy(비용 규율)
```

## 6. 비용 원칙

- CloudWatch 표준 지표(Lambda·RDS·SQS·ALB·Bedrock·Step Functions·S3)는 전부 각 서비스에 기본 포함 — 추가 요금 없음.
- EMF 커스텀 메트릭도 기존 Lambda 로그에 한 줄 추가하는 것뿐이라 추가 서비스 비용 없음(로그 저장량 미미).
- Bedrock invocation logging(프롬프트 전문 저장)은 **데모 캡처 구간에만 on**, 상시 금지.
- Prometheus/Grafana는 EKS가 떠 있는 세션에서만 의미 있음 — `apply → 확인 → destroy` 사이클 그대로 적용.

## 7. 알려진 갭 (2026-07-03 구현 반영 — §12 참고)

**`infra/monitoring` 폴더 안에서 구현 완료(아래는 전부 [x]):**

- [x] `local.lambda_names`에 `remediation` 추가(5→6종) — 위젯·에러 알람(`for_each`) 둘 다 자동 반영
- [x] Step Functions(`remediation` 상태머신) 위젯 추가
- [x] S3 감사 버킷(Object Lock) 위젯 추가
- [x] RDS FreeStorageSpace·SQS ApproximateAgeOfOldestMessage 위젯 추가
- [x] Bedrock(`AWS/Bedrock`, ModelId 디멘션) 위젯 신규 추가 + 비용 metric math 위젯(§2③.2)
- [x] `CnappAgentic/Engine` 네임스페이스 CloudWatch 위젯 6종(무디멘션 총계 4종 + SEARCH 기반 판정분포 1종 + SEARCH 기반 tool분포 1종, §13·§15 반영) 대시보드에 추가 — 계측 전까진 No data(정상)
- [x] CloudTrail → CloudWatch Logs 배관(§10) — 로그그룹·IAM 역할·output 2종
- [x] Teams 알림 전체 스택(§11) — SNS·Lambda(실코드)·시크릿·구독·알람 7종(§15에서 Bedrock 비용 가드레일 추가)
- [x] `terraform fmt`/`init -backend=false`/`validate` 3종 전부 통과(§12)
- [x] `engine/reasoning/orchestrator.py`의 `_emit_case_metrics` 계측(§2③.1) — **완료(당일 후속)**, 아래 항목에서 완료로 이동
- [x] 케이스별 Bedrock 비용(토큰) EMF + tool별 breakdown EMF + Bedrock 비용 알람(§15) — `engine/evidence/bedrock_planner.py`·`evidence.py`·`core/case.py`·`reasoning/orchestrator.py` 4개 파일

**apply 완료(2026-07-03, §16) 후 처리:**

- [x] `infra/monitoring` **실 apply 완료** — 27개 리소스 생성(0 변경·0 삭제), 대시보드 24위젯 실제 렌더링(API로 확인, y/x 겹침 없음) — §16
- [x] `gitops/argocd/app-monitoring.yaml` + `gitops/monitoring/kube-prometheus-stack-values.yaml` 신설 — `grafana_irsa_role_arn` 실값 반영 완료(§16)
- [x] CloudTrail 기존 트레일(`cnapp-org-trail`)에 `cloudtrail_log_group_arn`/`cloudtrail_cwl_role_arn` 1회 연결 — CLI로 완료(§16, 로그그룹 ARN에 `:*` 접미사 필요했던 함정 기록)
- [ ] apply 후: `teams_webhook_secret_arn`에 로테이션된 새 webhook URL을 `aws secretsmanager put-secret-value`로 1회 수동 주입 — **미착수, 실 webhook URL 필요**

**이 폴더 밖이라 구현 안 함 — 기록만(§12 "외부 폴더 후속 작업" 참고):**

- [ ] (선택) `infra/shared/db/schema.sql`에 `grafana_ro` 읽기전용 Postgres 롤 추가(§9 실무 디테일) — Grafana의 3번째 데이터소스(Postgres)로 tool-use 분포·MTTR 등 직접 SQL 조회하고 싶을 때만 필요, 지금 3축 설계엔 없어도 무방
- [ ] `kubectl apply -f gitops/argocd/app-monitoring.yaml` 실행 자체는 EKS에 ArgoCD가 부트스트랩된 뒤(`gitops/README.md` 부트스트랩 순서 4번) — 아직 미실행

## 8. 검증 이력

- **2026-07-02**: `main.tf`가 참조하는 `data.terraform_remote_state.{shared,pipeline,console,engine}` 출력값(`eks_oidc_provider_arn`·`eks_oidc_provider`·`alb_arn_suffix`) 전부 실제 존재 확인. RDS identifier(`${var.project}-pgvector`)·SQS 이름(`${var.project}-ingest[-dlq]`)·Lambda 5종 이름이 각 레이어의 실제 리소스 정의와 정확히 일치 확인. HCL 구문 파싱(python-hcl2) 통과. **위 §7 갭들은 이번 검증에서 신규 발견**(특히 remediation Lambda 누락은 2026-07-02 조치 실행기 추가 이후 대시보드에 반영이 안 된 것).

## 9. 준형 피드백 검증(2026-07-03)

준형이 보낸 관측 대시보드 아이디어(레이어 분리 판단 + 에이전트 관측 패널 4종 + 부가 후보 3종)를 실제 코드·스키마와 대조. **레이어 분리 판단·전반적 방향은 맞다.** 패널별로는 바로 되는 것과 선행 작업이 필요한 것이 갈린다.

| 제안 | 검증 결과 | 근거 |
|---|---|---|
| Managed Grafana 대신 self-hosted kube-prometheus-stack | ✅ 정확(가격만 사소 정정: Editor/Admin $9, Viewer $5/월, 자체호스팅은 $0) | AWS 공식 가격 페이지 |
| 모델별 토큰·비용(Bedrock native 지표) | ✅ 그대로 유효 | §2③ Tier1과 동일 |
| **트리아지 절감 효과 — `cases.model_trace` 재활용** | ⚠️ **부분적으로만 가능** — `model_trace`엔 stage·model은 실제로 기록되지만 **`tokens` 필드는 코드상 항상 0**(`engine/core/case.py`의 `_trace()`가 `tokens: int = 0` 기본값으로만 호출되고, 실제 토큰 사용량을 넘기는 호출이 레포 어디에도 없음) | `engine/core/case.py:58-59`, `set_triage/set_evidence/set_reasoning` 전부 `_trace(case, stage, model)`만 호출(3rd 인자 없음) |
| ㄴ (위 대안) escalate율만 볼 거면 | ✅ `cases.triage.escalate`는 실제 값이라 바로 가능 | `schema.sql` cases.triage jsonb |
| Evidence tool-use 분포 | ✅ `cases.evidence`(jsonb 배열, tool·resource_id·result_summary·ts) 실존 — SQL로 바로 집계 가능 | `schema.sql` |
| **allowlist 거부 카운트** | ❌ **지금 구조론 데이터가 아예 없음** — 툴 호출이 allowlist에 막히면 `ToolNotAllowed`를 잡아서 LLM에게 에러 텍스트로만 돌려주고(`_run_tool`), **거부 이벤트 자체를 `case`나 로그에 남기지 않음** | `engine/evidence/bedrock_planner.py:201-206`, `engine/core/tools.py:49-51` |
| verdict 분포·confidence 히스토그램 | ✅ `cases.evidence_meta` 실존 — 단 verdict enum은 `confirmed/refuted/inconclusive`(원문의 "false_positive"는 스키마에 없는 값, `refuted`가 맞음) | `engine/core/case.py:81`(validate_shape) |
| CloudTrail 감사 뷰 | ⚠️ **정정(2026-07-03): 트레일은 이미 있음** — `manual-infra.md` §1에 진우가 **수동으로 멀티리전 트레일을 이미 생성**(관리 이벤트 R/W·SSE-S3·로그파일 검증 ON, ✅ 완료). 콘솔에 보이는 S3가 그 트레일의 로그 버킷. **단, "SNS·CloudWatch Logs 연동 OFF"로 만들어놔서 지금은 S3에만 쌓이고 Grafana가 못 봄** → 신설이 아니라 **기존 트레일에 CloudWatch Logs 연동을 추가**하는 게 실제 남은 일(§10 참고) | `docs/manual-infra.md` §1(33행) |
| DLQ/SLO 패널 | ✅ SQS 위젯 이미 있음(§2②) — 보완 정도 | 기존 `main.tf` |
| finding 리드타임(MTTR) | ✅ `findings.first_seen`·`cases.created_at`·`remediation_requests.updated_at` 전부 존재 — SQL 한 방으로 가능 | `schema.sql` |
| X-Ray(보너스) | 동의 — 후순위로 미뤄도 됨 | — |

**Grafana PostgreSQL 데이터소스 관련 실무 디테일**: RDS 보안그룹이 VPC CIDR 전체에 5432를 열어놔서(`infra/shared/main.tf` `aws_security_group.rds`) EKS 안 Grafana에서 네트워크 경로는 문제없다. 다만 지금 있는 자격증명은 마스터 시크릿뿐이라 Grafana 전용 **읽기 전용 Postgres 롤**을 하나 새로 만들어야 한다(마스터 계정 그대로 물리는 건 최소권한 원칙 위반 — `schema.sql`에 `CREATE ROLE grafana_ro ... GRANT SELECT`류 한 블록 추가하면 끝, 큰 작업 아님).

**결론 — 착수 전 선행 작업 3개만 추가:**
1. `engine/evidence/bedrock_planner.py`(준형 파일)에서 Converse 응답의 `usage.inputTokens/outputTokens`를 `_trace()`에 실제로 넘기도록 수정 — **이건 준형과 조율 필요**(§2③과 달리 이번엔 진짜 준형 파일을 만져야 함).
2. 같은 파일의 `_run_tool` 예외 처리에서 `ToolNotAllowed` 발생 시 case에 거부 이벤트를 남기도록(또는 EMF 카운터로) 보강 — 역시 준형 파일.
3. ~~`aws_cloudtrail` 트레일 신설~~ → **이미 있음(수동, ✅). 대신 기존 트레일에 CloudWatch Logs 연동만 추가**(§10) — 이건 진우 단독으로 가능.

나머지(모델별 토큰 native 지표·tool 분포·verdict 분포·MTTR·DLQ)는 지금 스키마·코드 그대로 바로 대시보드화 가능.

## 10. CloudTrail → Grafana 연동 상세 (트레일 신설 아님 — 기존 트레일 활용)

### 10.0 트레일 자체는 계속 수동 관리로 — 전부 Terraform으로 옮기지 않는다

`manual-infra.md` 서두(§ 범위)가 수동 관리 대상을 "①계정·테넌트 초기 설정(Terraform 실행 전에 사람이 먼저 하는 것) ②Terraform 부트스트랩 ③설계상 Terraform 밖" 3종으로 분류하는데, CloudTrail은 **루트 MFA·IAM 사용자·Budgets와 같은 줄(§1)**, 즉 ①"계정 초기 설정"이다. 이 셋의 공통점 = **계정 전체에 걸리는 보안 베이스라인, 한 번 설정하고 거의 안 바뀌는 것, 그리고 무엇보다 "우리 자신의 `terraform destroy` 사이클에 절대 휘말리면 안 되는 것".**

이 프로젝트는 EKS·RDS 같은 비싼 레이어를 `apply → 확인 → destroy`로 계속 껐다 켠다(§6 비용 규율). 만약 감사 트레일까지 그 레이어 안에 넣으면, `terraform destroy infra/monitoring` 한 번 잘못 돌렸다가 감사 로그 연속성이 끊기는 리스크가 생긴다 — **감사 통제는 그 통제를 받는 시스템의 destroy 사이클 바깥에 있어야 한다**는 건 실무에서도 통하는 원칙(CloudTrail 로그 버킷에 흔히 Object Lock을 걸어 트레일 소유자조차 못 지우게 하는 것과 같은 맥락). 그래서 **트레일 자체는 계속 수동(현행 유지)**, 아래 새로 만드는 로그 그룹·IAM 역할만 Terraform(`infra/monitoring`)으로 — 이건 감사 통제의 핵심이 아니라 "Grafana가 보게 해주는 배관"일 뿐이라 이 레이어가 destroy돼도 트레일은 계속 S3에 잘 쓰고 있다(로그 그룹만 사라짐 → 재생성해도 이름이 고정이라 ARN이 동일해서 트레일 쪽 연결은 안 끊긴다).

**요약: 전부 콘솔도, 전부 Terraform도 아니고 — "보안 베이스라인(트레일)=수동, 그 위에 얹는 연동 배관(로그그룹·역할)=Terraform"으로 나누는 게 이 프로젝트 기존 관례(manual-infra.md 분류)와도, 감사 시스템 설계 원칙과도 맞다.**

**전제:** 트레일 자체(멀티리전·관리이벤트 R/W·SSE-S3)는 이미 수동으로 만들어져 있다(`manual-infra.md` §1). 콘솔에서 보이는 S3 버킷은 그 트레일의 로그 저장소 — 맞게 보고 있는 것. 근데 만들 때 "SNS·CloudWatch Logs 연동 OFF"로 해놔서, 지금은 로그가 S3에만 쌓이고 Grafana(CloudWatch datasource)는 S3 안을 못 들여다본다. **새로 만들 건 트레일이 아니라 "트레일 → CloudWatch Logs" 배달 경로 하나뿐이다.**

### 두 가지 방법 비교

| 방법 | 필요한 것 | 장점 | 단점 |
|---|---|---|---|
| **A. 기존 트레일에 CloudWatch Logs 연동 추가(권장)** | 새 로그 그룹 + 트레일이 assume할 IAM 역할(트러스트: `cloudtrail.amazonaws.com`) | Grafana IRSA 역할(`aws_iam_role.grafana`)이 **이미** `logs:StartQuery`·`GetQueryResults` 권한을 갖고 있어서(§1 IRSA 정책) **Grafana 쪽은 코드 변경 0** — Logs Insights 쿼리만 추가하면 끝. 새 Grafana 플러그인도 불필요. | 기존 트레일을 수정해야 하는데, 트레일이 Terraform state 밖(수동 생성)이라 마지막 연결 단계는 **콘솔에서 수동으로 한 번**(또는 `terraform import` 후 관리) 해야 함 |
| B. S3 위에 Athena로 직접 쿼리 | Glue 테이블(CloudTrail 콘솔 "Create Athena table" 버튼) + Athena 결과용 S3 버킷 + **Grafana에 `grafana-athena-datasource` 플러그인 설치** + Grafana IRSA에 Athena/Glue 권한 추가 | 기존 트레일 설정을 전혀 안 건드림 | 움직이는 부품이 더 많음(플러그인 설치·새 IAM·새 버킷) — 지금 이미 CloudWatch Logs 권한을 깔아둔 상태에서 굳이 갈 이유가 약함 |

**A안 추천.** 지금 세팅된 것(Grafana의 CloudWatch Logs 권한)을 그대로 쓰는 게 제일 적은 변경.

### A안 — 만들 것 (`infra/monitoring/main.tf`에 추가)

```hcl
resource "aws_cloudwatch_log_group" "cloudtrail" {
  name              = "/aws/cloudtrail/${var.project}"
  retention_in_days = var.log_retention_days   # 다른 레이어와 동일 관례(14일)
}

data "aws_iam_policy_document" "cloudtrail_cwl_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
  }
}
resource "aws_iam_role" "cloudtrail_cwl" {
  name               = "${var.project}-cloudtrail-to-cwl"
  assume_role_policy = data.aws_iam_policy_document.cloudtrail_cwl_trust.json
}
data "aws_iam_policy_document" "cloudtrail_cwl_write" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.cloudtrail.arn}:*"]
  }
}
resource "aws_iam_role_policy" "cloudtrail_cwl" {
  name   = "write"
  role   = aws_iam_role.cloudtrail_cwl.id
  policy = data.aws_iam_policy_document.cloudtrail_cwl_write.json
}

output "cloudtrail_log_group_arn" { value = aws_cloudwatch_log_group.cloudtrail.arn }
output "cloudtrail_cwl_role_arn"  { value = aws_iam_role.cloudtrail_cwl.arn }
```

`var.log_retention_days`(기본 14, 다른 레이어와 통일)를 `infra/monitoring/variables.tf`에 추가.

### 마지막 수동 연결(트레일이 Terraform 밖이라 1회만)

`terraform apply` 후 나온 `cloudtrail_log_group_arn`·`cloudtrail_cwl_role_arn` 두 값을 CloudTrail 콘솔 → 기존 트레일 편집 → "CloudWatch Logs" 섹션에 붙여넣기. (원하면 나중에 `terraform import aws_cloudtrail.this <trail-arn>`으로 트레일 자체도 Terraform 관리로 편입 가능 — 지금은 필수 아님.)

### Grafana 쪽 — 새 위젯 없이 Logs Insights 쿼리만

필터 대상 IAM 역할은 확인 완료: **`cnapp-agentic-engine-orchestrator`**(Evidence/Bedrock 실 호출 Lambda 역할, `infra/backend/main.tf`). 예시 쿼리:

```
fields eventTime, eventName, userIdentity.sessionContext.sessionIssuer.userName, requestParameters
| filter userIdentity.sessionContext.sessionIssuer.userName = "cnapp-agentic-engine-orchestrator"
| sort eventTime desc
```

이 쿼리 결과가 그대로 "AI 에이전트가 실제로 호출한 API 타임라인" 패널이 된다.

## 11. Teams 알림 (CloudWatch Alarms → SNS → Teams)

### 🔴 먼저: 기존 웹훅 URL 노출 건 (긴급, 이 레이어 설계와 별개)

검증 중 발견 — `docs/manual-infra.md`에 Teams(Power Automate) 웹훅 URL이 서명값까지 포함해 평문으로 커밋돼 있었고, **이 레포는 GitHub public**이라 인터넷에 그대로 노출된 상태였다. 문서는 방금 레닥션했지만(§ manual-infra.md 3.5), **실제 무력화는 Power Automate에서 웹훅을 재생성(로테이션)해야만 끝난다** — 이건 코드로 못 고치는 부분이라 직접 처리 필요. 로테이션 전까지는 그 채널로 아무 알림도 신뢰하지 말 것.

### 설계 원칙 — §10과 동일한 분리

- **웹훅 URL 값 자체(민감정보) = 수동**(Secrets Manager에 로테이션 후 값만 넣기 — Terraform state에 절대 안 남게).
- **알림 배관(SNS·Alarms·전달 Lambda) = Terraform**(`infra/monitoring`, 이 레이어 destroy돼도 트레일과 마찬가지로 시크릿 값 자체는 Secrets Manager에 안전하게 남음).

### 무엇을 만드나

```
aws_secretsmanager_secret.teams_webhook          # 값은 Terraform이 아니라 로테이션 후 콘솔/CLI로 1회 주입
aws_sns_topic.alerts                             # CloudWatch Alarms의 공통 팬아웃 지점
aws_iam_role.teams_notifier + policy             # secretsmanager:GetSecretValue(이 시크릿 ARN만)
aws_lambda_function.teams_notifier               # SNS 구독 → 시크릿 조회 → Teams Adaptive Card POST
aws_sns_topic_subscription (sns → lambda)
aws_cloudwatch_metric_alarm × N                  # 아래 표, alarm_actions = [sns_topic.alerts.arn]
```

### 알람 후보(알림 피로 방지 — 진짜 조치가 필요한 것만)

| 알람 | 조건(예시) | 왜 |
|---|---|---|
| SQS DLQ 적재 | `ingest-dlq` ApproximateNumberOfMessagesVisible > 0 | 정규화 실패 finding 존재 = 데이터 유실 위험 |
| Lambda 에러율 | 6종 중 아무 Errors > 0 (5분 합) | 파이프라인 끊김 |
| Step Functions 실패 | `remediation` ExecutionsFailed > 0 | HITL 조치가 실패했는데 아무도 모르는 상황 방지 |
| Bedrock 에러 | `AWS/Bedrock` InvocationClientErrors/ServerErrors > 0 | AI 조사 자체가 멈췄다는 신호 |
| RDS 연결 포화 | DatabaseConnections > 임계치 | 조용히 장애로 번지기 전에 |
| (커스텀) escalate율 0 지속 | `CnappAgentic/Engine` FindingsEscalated 합이 N분간 0인데 FindingsEvaluated > 0 | 트리아지 게이트가 조용히 다 걸러버리는 회귀(§2③ EMF) 감지 |
| (커스텀, §15) Bedrock 비용 가드레일 | 토큰×단가 metric math(시간당) > `var.bedrock_hourly_cost_alarm_usd`(기본 $1.0) | 무한루프·비정상 다량 tool-use 조기 감지 — 정밀 예산 통제가 아니라 안전망 |

나머지(ALB 5xx, CloudFront 등)는 알람보다 대시보드 관찰로 충분 — 전부 알람 걸면 데모 중 알림 폭탄이라 위 표 정도로 시작.

### 왜 Lambda가 SNS와 Teams 사이에 필요한가

SNS는 Teams webhook이 기대하는 Adaptive Card JSON 포맷을 직접 못 만든다 — SNS raw 메시지를 그대로 포워딩하면 Teams가 안 예쁘게 뿌리거나 무시함. 그래서 최소 변환 Lambda 하나가 필요(SNS 메시지 파싱 → 카드 포맷 → requests.post). 이 Lambda 자체는 이미 짜둔 다른 Lambda들과 같은 패턴(`infra/monitoring`에 archive_file 스텁으로 배포, 실코드는 나중).

## 12. 구현 완료 로그 (2026-07-03)

§1~11 설계를 `infra/monitoring` 폴더 안에서 전부 코드화했다. **원칙: 이 폴더만 건드리고, 다른 폴더가 필요한 항목은 구현하지 않고 기록만 남긴다.**

### 12.1 이번에 만든 것 (`main.tf`/`variables.tf`/`outputs.tf`/`lambda_src/`)

| 구분 | 내용 |
|---|---|
| 대시보드 위젯 | 기존 4개(Lambda 5·SQS·RDS·ALB) → 확장: Lambda 6종(remediation 추가)·SQS 깊이/백로그나이·RDS CPU연결/스토리지IOPS·ALB·SFn(remediation)·S3 감사버킷·Cognito 로그인·Bedrock 호출지연/에러토큰(모델별)·Bedrock 비용(metric math)·엔진 EMF 4종(SEARCH 기반)[^widget-count] |
| CloudTrail 연동 | 로그그룹(`/aws/cloudtrail/${project}`) + IAM 역할(`cloudtrail.amazonaws.com` assume) + write 정책 + output 2종(§10 A안 그대로) |
| Teams 알림 | Secrets Manager(값 없음, 수동 주입 전제) · SNS 토픽 · Lambda(`lambda_src/teams_notifier.py`, **실코드** — SNS→Adaptive Card 변환→webhook POST, stdlib+boto3만) · SNS→Lambda 구독/권한 |
| 알람 | SQS DLQ·Lambda 에러(6종 `for_each`)·SFn 실패·Bedrock 에러(metric math)·RDS 연결포화·트리아지 게이트 0건(2026-07-03 §13에서 SEARCH 제거, EMF 계측 전엔 INSUFFICIENT_DATA로 대기) — 전부 `alarm_actions=[sns.alerts]` |
| 변수 | `log_retention_days`·Bedrock 단가 4종·`rds_connections_alarm_threshold` (`cloudfront_distribution_id` 변수는 2026-07-03 §14에서 삭제 — remote_state 직접 참조로 대체) |

[^widget-count]: **당시 "17개"로 적었던 건 오기재.** Lambda·Bedrock 위젯은 `for` 루프 1개가 여러 개(각 6개·모델 수만큼)를 만드는데 "루프문 1줄=위젯 1개"로 잘못 세어 축소 집계했음 — 실제로는 22개(§3·§14 참고, 2026-07-03 재검산).

### 12.2 설계 대비 판단 — Grafana Postgres 데이터소스(§9)는 이번 스코프 밖으로 제외

§9 검증 노트가 "Grafana 전용 읽기전용 Postgres 롤"을 언급했지만, §1의 하이브리드 3축 설계(Prometheus+CloudWatch) 자체엔 Postgres 데이터소스가 없다 — §9는 준형이 제안한 "case 테이블 직접 SQL 조회" 아이디어에 대한 실무 메모였지 §1~3의 확정 설계가 아니다. **schema.sql 변경(다른 폴더)까지 필요해서 이번엔 구현하지 않고 §7에 옵션으로만 기록** — 지금 3축 대시보드로 필요한 관측은 다 커버되고, EMF(§2③)가 이미 case 단위 지표(tool-use·확신도·판정분포)를 담당하므로 우선순위가 낮다고 판단.

### 12.3 검증 결과

```
terraform fmt -check   → 통과(수정 없음)
terraform init -backend=false → 통과(aws 5.100.0, archive 2.8.0)
terraform validate     → Success! The configuration is valid.
python -m py_compile lambda_src/teams_notifier.py → 통과
```

`.terraform/`·`.terraform.lock.hcl`·`build/`는 다른 레이어와 동일하게 검증 후 삭제(레포 gitignore 대상, 커밋 안 함).

**검증 못한 것(라이브 AWS 필요, 구조적 한계 — `infra/README.md`의 "4층 plan은 shared apply 후"와 동일 사유):**
- `terraform plan`은 `data.terraform_remote_state.{pipeline,console,engine}`이 가리키는 state 파일이 apply 전이라 아직 없어서 실행 불가(내일 4개 레이어 apply 후에만 가능) — 이건 버그가 아니라 레이어드 구조상 당연한 순서.
- 대시보드 위젯 JSON의 실제 렌더링(디멘션 이름 정확도 등, 예: `AWS/Cognito`의 `UserPool` 디멘션 키)은 CloudWatch가 JSON 스키마 자체를 apply 시점에 검증하지 않아 `terraform validate`로는 못 잡음 — 틀려도 apply는 성공하고 위젯이 "No data"로만 보임(장애 아님). **apply 후 대시보드 콘솔에서 육안 확인 필요.**
- EMF 기반 위젯·알람(엔진 축) 4+1개는 `engine/reasoning/orchestrator.py` 계측 전까지 데이터가 없는 게 정상 — 계측 후 실데이터로 재확인 필요.

### 12.4 외부 폴더 후속 작업 (기록만 — 이번 세션에서 구현 안 함)

1. ~~`engine/reasoning/orchestrator.py` EMF 계측~~ → **완료(2026-07-03, 같은 날 후속 작업)**. §3.1·§13 참고.
2. **`gitops/argocd/app-monitoring.yaml` + `gitops/monitoring/kube-prometheus-stack-values.yaml`**(§4) — Grafana SA에 `grafana_irsa_role_arn` output 주입하는 Helm values + ArgoCD Application. `infra/monitoring` apply 후 이 값을 받아서 작성.
3. ~~`infra/console/outputs.tf`에 `cloudfront_distribution_id` output 추가~~ → **완료(2026-07-03, 준형이 반영)**. `main.tf`의 `local.cloudfront_distribution_id`가 이제 이 값을 직접 참조하고, CloudFront 위젯도 변수 게이트 없이 상시 포함되도록 갱신함(`variables.tf`의 임시 게이트 변수는 삭제).
4. **(선택) `infra/shared/db/schema.sql`**에 `grafana_ro` 롤 추가 — §12.2 사유로 이번엔 보류.
5. **`docs/manual-infra.md`** — apply 후 실제로 완료되면: ① CloudTrail→CWLogs 수동 연결 완료 기록(§10 마지막 단계) ② Teams 웹훅 로테이션·Secrets Manager 주입 완료 기록(이미 §3.5에 레닥션·조치안내는 있음, "완료" 체크만 남음). 사소한 참고: 이번에 만든 시크릿 이름은 `${project}/teams/webhook`(슬래시, RDS 시크릿과 동일 컨벤션) — manual-infra.md §3.5의 예시 문구(`cnapp-agentic-teams-webhook`, 대시)와 표기가 다르니 나중에 맞추면 됨(기능엔 영향 없음).

## 13. 재검증(2026-07-03) — 전체 재점검에서 발견·수정한 버그 3건

배포 전 처음부터 다시 정독하며 찾은 것. **셋 다 이번에 수정 완료**, 아래는 기록.

| # | 버그 | 왜 문제인가 | 수정 |
|---|---|---|---|
| 1 | `triage_escalate_rate_zero` 알람의 `metric_query.expression`이 `SUM(SEARCH(...))`를 씀 | **CloudWatch 알람은 metric math에서 `SEARCH()` 함수를 지원하지 않는다**(대시보드 위젯에서만 허용 — 동적으로 시계열 개수가 변하는 함수라 단일 임계값 알람과 안 맞음). `terraform validate`는 이걸 못 잡는다(HCL 스키마만 검사, AWS API 시맨틱 검증은 apply 때 발생) — 그대로 뒀으면 apply 시 이 알람 리소스 생성이 API 레벨에서 거부됐을 가능성이 큼 | `_emit_case_metrics`가 `Dimensions=[[], ["Verdict","RiskLevel"]]`로 무디멘션 총계 시계열도 같이 발행하도록 수정 → 알람은 SEARCH 없이 이 무디멘션 메트릭을 `metric_query.metric` 블록으로 직접 참조(§3.1) |
| 2 | `bedrock_errors` 알람이 `AWS/Bedrock` 지표를 `ModelId` 디멘션 없이 조회 | Bedrock CloudWatch 지표는 ModelId별로만 발행되고 무디멘션 롤업이 없다(Lambda의 `Invocations`가 FunctionName 없이는 존재하지 않는 것과 동일) — 디멘션 없이 조회하면 데이터가 영원히 안 잡혀 알람이 계속 INSUFFICIENT_DATA(기능적으로 죽은 알람, apply는 성공하지만 절대 안 울림) | `client_err`·`server_err` 두 `metric_query.metric`에 `dimensions = { ModelId = local.bedrock_model_ids[0] }` 추가(모델 1개뿐이라 `[0]` 고정 — Sonnet 추가 시 `lambda_errors`처럼 `for_each` 전환 고려, 주석에 명시) |
| 3 | Bedrock 모델별 위젯이 `y = 42 + j*6`로 모델 수만큼 동적으로 늘어나는데, 그 아래 비용/EMF/CloudFront 위젯 y좌표는 **하드코딩**(48·54·60·66) | "리스트에 모델만 추가하면 자동 확장"이 설계 의도였는데 실제로는 안 됨 — Sonnet이 추가되면(모델 2개) Bedrock 위젯이 y=42~54를 차지해 비용 위젯(y=48 고정)과 겹침. §7(알려진 갭)에서 "스켈레톤 완성"이라고 표시했던 것과 실제 코드가 안 맞았던 사례 | `local.bedrock_rows_end_y = 42 + length(bedrock_model_ids) * 6` 신설, 비용·EMF·CloudFront 위젯 y를 전부 이 값 기준 상대좌표로 변경 — 지금(모델 1개)은 기존과 동일한 y값(48·54·60·66)이 나오되, 모델이 늘어도 자동으로 밀림 |

**재검증 방법:** `terraform fmt`+`init -backend=false`+`validate` 재통과, `python -m py_compile`+`run_demo`+`run_e2e` 무회귀 재확인(오늘 3번째 라운드). 셋 다 실제 AWS 지식(Bedrock 디멘션 스키마·CloudWatch 알람 함수 제약)에 기반한 논리 검증이라 **apply 전 라이브 재확인은 여전히 못 함**(§12.3과 동일한 구조적 한계) — 다만 SEARCH 제거는 AWS 공식 문서에 명시된 제약이라 신뢰도 높음, Bedrock 디멘션·Cognito 디멘션 키 등은 그대로 "라이브 미검증" 상태(§12.3).

## 14. CloudFront 게이트 해제 (2026-07-03, 후속)

§7·§12.4에서 "`infra/console`에 output이 없어 대기 중"이라 기록했던 것 — 준형이 `infra/console/outputs.tf`에 `cloudfront_distribution_id` output을 추가해줘서(`7a8c609`) 더는 대기할 이유가 없어졌다. 반영한 것:

- `main.tf`의 `locals`에 `cloudfront_distribution_id = data.terraform_remote_state.console.outputs.cloudfront_distribution_id` 추가 — 다른 remote_state 참조(`alb_arn_suffix`·`cognito_user_pool_id`)와 동일한 패턴.
- CloudFront 위젯을 감싸던 `var.cloudfront_distribution_id != "" ? [...] : []` 조건부 삼항 제거 — **레이어 순서(`infra/console`이 `infra/monitoring`보다 항상 먼저 apply, §5)상 이 값은 apply 시점에 항상 존재**하므로 더는 게이트가 필요 없다. CloudFront 위젯이 이제 상시 대시보드에 포함된다.
- `variables.tf`의 임시 게이트 변수 `cloudfront_distribution_id`(기본값 `""`)는 삭제 — 더는 쓰이지 않음.

`terraform fmt`/`init -backend=false`/`validate` 재통과(`infra/monitoring`·`infra/console` 둘 다) 확인.

**부수 발견 — 위젯 개수 오기재.** 이 김에 `main.tf`의 `type = "metric"` 위젯을 실제로 다시 세어보니(Lambda 6종은 `for` 루프 1개가 6개 위젯을 만들고, Bedrock 2종도 각 `for` 루프 1개가 모델 수만큼 만드는 걸 그동안 "루프문 1줄=위젯 1개"로 착각해 계속 축소 집계했었다), §3·§12.1 등에 반복해서 적었던 "17개"(CloudFront 추가 후 "18개")가 **처음부터 잘못된 숫자**였음을 발견 — 실제로는 **22개**(Lambda 6 + 인프라 8 + Bedrock 2 + 비용 1 + 엔진 EMF 4 + CloudFront 1, §15에서 24개로 다시 늘어남). §3 표는 이 문서에서 정정했고, `CLAUDE.md`·루트 `README.md`·`troubleshooting.md`에 남아있는 "17위젯" 언급은 그 시점 기록(changelog)이라 그대로 두되, 살아있는 현재상태 문서(루트 README 구현현황 표 등)는 별도로 정정이 필요하다.

---

## 15. AI 관측 3종 추가 (2026-07-03, 후속) — 비용 알람·케이스별 비용·tool별 breakdown

§7(알려진 갭)에서 "있으면 좋지만 급하진 않다"로 남겨뒀던 3가지를 전부 코드로 채움. 셋 다 apply·EKS 없이 지금 만들 수 있는 순수 코드 변경이었다(§2③가 이미 "케이스 단위 지표는 `Orchestrator.run()` 안에서 다 뽑아낼 수 있다"고 정리해둔 것의 연장선).

### 15.1 비용 알람 (`bedrock_cost_high`)

지금까지 §3.2 비용 위젯은 **보기만 하는 것**이었지 임계값 초과 시 알려주는 알람이 아니었음 — 이 프로젝트가 비용 통제를 핵심 원칙으로 삼는데 정작 Bedrock 비용엔 가드레일이 없던 공백. `main.tf`에 `aws_cloudwatch_metric_alarm.bedrock_cost_high` 신설 — 비용 위젯과 **동일한 metric math 식**(토큰×단가)을 재사용하되 `period`만 300(위젯, 추세용)→3600(알람, 시간당 예산 개념)으로 바꿔 스파이크 오탐을 줄임. 임계값은 새 변수 `var.bedrock_hourly_cost_alarm_usd`(기본 $1.0/시간 — 정밀 예산 통제가 아니라 "무한루프·비정상 다량 호출" 조기 감지용 안전망, 데모 규모 기준 여유값). Teams 알림 경로(SNS→Lambda)에 그대로 연결.

### 15.2 케이스별 Bedrock 토큰 (비용 귀속)

문제: 기존 비용 위젯(§3.2)은 **계정×모델 전체 합산**이라 "이 조사 하나에 얼마 썼는지"를 알 수 없었음. 해결 경로(전부 `infra/monitoring` 밖 — engine 파일 3개 수정):

1. `engine/evidence/bedrock_planner.py`(`BedrockEvidenceAgent.investigate()`) — Bedrock `converse()` 응답에는 이미 `usage.inputTokens`/`outputTokens`가 들어있는데 그동안 안 꺼내 씀. tool-use 루프는 케이스 1건당 여러 번 반복 호출되므로(LLM이 도구를 여러 번 쓸 수 있어서) **루프 반복마다 누적**해야 케이스 전체 토큰이 나옴 — 초기 구현 때 놓치기 쉬운 지점.
2. `engine/evidence/evidence.py` — `EvidenceOutput`에 `input_tokens`/`output_tokens: int = 0` 필드 추가(규칙 플래너 `EvidenceAgent`는 LLM을 안 써서 기본값 0 그대로 반환 — 회귀 없음).
3. `engine/core/case.py` — `set_evidence()`에 `tokens: int = 0` 파라미터 추가, `case.schema.json`이 **처음부터 정의해뒀지만 지금까지 항상 0으로 방치돼 있던** `model_trace[].tokens`(설명: "단계별 Bedrock 모델·토큰, 비용 추적")에 실제 값을 채움 — 새 스키마 필드가 아니라 **기존 계약의 미사용 필드를 메운 것**.
4. `engine/reasoning/orchestrator.py` — `_emit_case_metrics`에 `BedrockInputTokens`/`BedrockOutputTokens` 파라미터·EMF 메트릭 추가(기존 `Dimensions=[[], ["Verdict","RiskLevel"]]` 그대로 재사용, 집계용).

**설계 결정 — CaseId는 지표 Dimension으로 넣지 않음.** 케이스마다 값이 달라 무한정 늘어나는 카디널리티라 안티패턴(CloudWatch 커스텀 메트릭 요금도 유니크 dimension 조합당 과금). 대신 EMF 로그 원본엔 `CaseId`가 필드로 이미 찍히므로, **"이 케이스 하나에 얼마 썼는지"는 CloudWatch Logs Insights로 로그를 `CaseId`로 검색해서 본다** — 지표(위젯)는 집계용, 로그(Logs Insights)는 케이스 단위 드릴다운용으로 역할을 분리.

### 15.3 tool별 호출 breakdown

`EvidenceOutput.plan`(`(tool, resource_id)` 목록)이 **이미 존재하는 필드**였음 — 규칙 플래너·LLM 플래너 둘 다 채우고 있었는데 "설명용"으로만 쓰이고 관측엔 한 번도 안 흘러갔던 걸 발견. `orchestrator.py`에 `_emit_tool_usage_metrics(case_id, plan)` 신설 — `Counter`로 tool별 호출 횟수를 집계해 **tool마다 별도 EMF 라인**을 찍음(`Dimensions=[["Tool"]]`). EMF는 한 로그 라인 = 한 Dimension 값 세트라, 케이스 하나에서 tool 여러 종류가 호출됐으면 총계 지표처럼 한 줄로 못 묶고 tool 수만큼 라인이 필요함 — 판정 분포 위젯과 마찬가지로 대시보드에선 `SEARCH('{CnappAgentic/Engine,Tool} MetricName="ToolInvocations"', 'Sum', 300)`로 Tool별 시계열을 펼쳐서 봄.

### 15.4 위젯 레이아웃 갱신

엔진 EMF 위젯 2개(케이스별 토큰·tool breakdown)를 기존 4개 뒤, CloudFront 앞에 삽입 — `y = bedrock_rows_end_y + 18`(가로 2개), CloudFront는 `+ 24`로 밀림. 대시보드 총 위젯 **22개 → 24개**(엔진 EMF 4종 → 6종). §3·§12.1 표 갱신 완료.

### 15.5 검증

오프라인 fake Bedrock 클라이언트로 2턴 tool-use 루프(1턴째 tool 2개 호출+usage 500/120, 2턴째 end_turn+usage 300/80)를 재현해 `input_tokens==800`·`output_tokens==200`(누적 확인)·`model_trace[-1]["tokens"]==1000`·EMF 출력 JSON 형태(총계 라인 1개 + tool별 라인 2개) 전부 확인. `engine.run_demo`·`run_e2e`·`contracts validate` 무회귀(Lambda 밖이라 미발행 그대로). `infra/monitoring` `fmt`+`init -backend=false`+`validate` 재통과.

⚠️ 위 §7 알려진 갭과 동일한 한계 — 실 Bedrock/Lambda가 돌아가기 전까진 이 6개 EMF 위젯·`bedrock_cost_high` 알람 다 "No data"/`INSUFFICIENT_DATA`가 정상.

---

## 16. 실 apply 완료 (2026-07-03) — 준형 4개 레이어(shared·target·console·backend) 이후

준형이 `infra/shared`·`infra/target`·`infra/console`·`infra/backend`(§ pipeline+engine 병합, `e806ee6`) apply를 끝낸 직후 이 레이어를 처음으로 실제 apply했다.

### 16.1 apply 결과

`terraform plan` → **27 to add, 0 to change, 0 to destroy**(순수 신규 생성, 기존 레이어 무영향) → `apply` 성공. Outputs 전부 발급 확인:

```
grafana_irsa_role_arn    = arn:aws:iam::066107819776:role/cnapp-agentic-monitoring-grafana-irsa
dashboard_url            = https://ap-northeast-2.console.aws.amazon.com/cloudwatch/home?region=ap-northeast-2#dashboards:name=cnapp-agentic-platform
teams_webhook_secret_arn = arn:aws:secretsmanager:ap-northeast-2:066107819776:secret:cnapp-agentic/teams/webhook-V5Ec2l
cloudtrail_log_group_arn = arn:aws:logs:ap-northeast-2:066107819776:log-group:/aws/cloudtrail/cnapp-agentic
cloudtrail_cwl_role_arn  = arn:aws:iam::066107819776:role/cnapp-agentic-cloudtrail-to-cwl
alerts_sns_topic_arn     = arn:aws:sns:ap-northeast-2:066107819776:cnapp-agentic-monitoring-alerts
```

### 16.2 대시보드 실제 렌더링 검증 (§13 캐비어트가 우려했던 부분)

§13/§7에서 "위젯 JSON의 AWS 시맨틱은 `terraform validate`로 못 잡고 apply 후 육안 확인이 필요하다"고 적어뒀던 것 — boto3 없는 환경이라 CLI로 대신 확인(`aws cloudwatch get-dashboard` → `DashboardBody` JSON 파싱). **결과: 정확히 24개 위젯, 설계한 y/x 좌표 그대로 겹침 없이 등록됨**(Lambda 6 → 인프라 8 → Bedrock 2 → 비용 1 → 엔진 EMF 6 → CloudFront 1). `dashboard_url` 콘솔 화면으로 진짜 렌더링(그래프 표시)까지는 별도 확인 필요하지만, JSON 스키마 레벨(디멘션 이름 등)은 AWS가 리소스 생성을 거부하지 않았다는 것으로 최소 검증됨.

⚠️ Windows 콘솔(cp949)에서 `aws cloudwatch get-dashboard`가 한국어 위젯 제목의 em-dash(—, U+2014)를 못 인코딩해 크래시하는 함정 발견 — `PYTHONUTF8=1 PYTHONIOENCODING=utf-8` 환경변수로 우회(다른 Python 스크립트들의 `sys.stdout.reconfigure(encoding="utf-8")`와 같은 계열의 Windows 콘솔 인코딩 문제).

### 16.3 CloudTrail → CloudWatch Logs 연결 (§10·§7 마지막 수동 단계)

`aws cloudtrail describe-trails`로 실제 트레일명이 `cnapp-org-trail`(manual-infra §1과 일치)임을 확인 후 CLI로 연결:
```
aws cloudtrail update-trail --name cnapp-org-trail \
  --cloud-watch-logs-log-group-arn "<cloudtrail_log_group_arn>:*" \
  --cloud-watch-logs-role-arn "<cloudtrail_cwl_role_arn>"
```
**함정**: 처음 `:*` 접미사 없이 보냈다가 `InvalidCloudWatchLogsLogGroupArnException`로 실패 — CloudTrail의 `CloudWatchLogsLogGroupArn`은 로그 스트림 와일드카드(`:*`)가 붙은 형태를 요구한다(로그그룹 자체 ARN이 아님). `terraform output`이 주는 순수 로그그룹 ARN에 `:*`를 붙여서 재시도 후 성공. **트레일 자체는 Terraform state 밖**(§10 설계 그대로) — 이 명령은 `infra/monitoring`의 tfstate에 아무 영향 없음(순수 AWS API 호출), 트레일의 "로그 전달 대상"만 갱신.

### 16.4 gitops/monitoring 신설 (§14의 "진짜 blocked" 해소)

`grafana_irsa_role_arn`이 실제 값으로 나온 시점에 바로 착수:
- **`gitops/monitoring/kube-prometheus-stack-values.yaml`** — Grafana ServiceAccount에 위 IRSA role-arn 주석(annotation), CloudWatch를 `additionalDataSources`로 추가(`authType: default`로 IRSA 자동 인증), Alertmanager는 비활성화(CloudWatch Alarms→SNS→Teams가 이미 커버 — 중복 방지·리소스 절감), Prometheus/Grafana 둘 다 영구볼륨 없이 소형 리소스(데모 규모 spot 노드 기준).
- **`gitops/argocd/app-monitoring.yaml`** — `app-target.yaml`과 소스 구조가 다름: 이건 **멀티소스 Application**(ArgoCD 2.6+)으로, 소스①=공식 `prometheus-community/kube-prometheus-stack` Helm 차트, 소스②=이 레포(`ref: values`, 위 values 파일만 제공). `$values/gitops/monitoring/kube-prometheus-stack-values.yaml` 참조로 두 소스를 묶는다.
- **IAM 역할 이름이 고정값(랜덤 접미사 없음)**이라 apply→destroy를 반복해도 ARN이 안 바뀜 — 이 values 파일은 한 번만 쓰면 되고, 재apply 때마다 갱신할 필요 없음(대화 중 미리 확인해둔 설계 근거, `main.tf`의 `aws_iam_role.grafana` `name` 참고).
- 아직 안 한 것: `kubectl apply -f gitops/argocd/app-monitoring.yaml` 실행 자체(ArgoCD가 EKS에 부트스트랩된 뒤 — `gitops/README.md` 순서 4번, 다음 세션).

### 16.5 남은 것

- Teams webhook secret에 실제 URL 값 수동 주입(로테이션된 URL 필요 — 아직 미착수)
- `kubectl apply -f gitops/argocd/app-monitoring.yaml`로 실제 Grafana 배포·CloudWatch 데이터소스 연결 확인
- `engine`/`backend` Lambda가 실제로 finding을 처리하기 시작하면 EMF 위젯·알람 실데이터 재확인
- `kube_bench.scan_cluster()`/`trivy.scan_image()` 등 EKS 필요한 실 스캐너 경로 검증(별도 작업, `scanners/workload/README` 참고)

## 17. 일일 비용 알림 + 콘솔 로그인 알림 (2026-07-06 추가)

사용자 요청("아침 9시마다 하루 사용 비용 알림 + 로그인 감지, 로그인은 사용자 이름 포함") 반영. 둘 다 **CloudWatch 알람이 아니라 능동 Lambda**로 구현 — 이유는 각 절 참고. 두 Lambda 모두 같은 `aws_sns_topic.alerts`에 발행해 기존 `teams_notifier`(§11) 경로를 그대로 재사용한다(신규 SNS 구독 불필요).

### 17.1 일일 비용 알림 (`daily_cost_notifier`)

- **왜 알람이 아니라 Lambda인가:** CloudWatch 알람은 "임계값 초과 여부"만 판단하는 모델이라 "매일 정기 리포트"(항상 보고할 값이 있음)와 안 맞는다. 대신 EventBridge 스케줄로 매일 트리거되는 Lambda가 Cost Explorer에서 전날 비용을 직접 조회해 SNS로 발행.
- **스케줄:** `aws_cloudwatch_event_rule.daily_cost_schedule` — `cron(0 0 * * ? *)`(UTC 00:00 = **KST 09:00**).
- **⚠️ Cost Explorer 리전 제약:** `ce:GetCostAndUsage` API 엔드포인트는 계정/Lambda 리전과 무관하게 **us-east-1 고정**(AWS 자체 제약) — `lambda_src/daily_cost_notifier.py`가 `boto3.client("ce", region_name="us-east-1")`로 명시. Lambda 함수 자체는 그대로 서울에 배포.
- **IAM:** `ce:GetCostAndUsage`는 리소스 레벨 권한을 지원하지 않아 `Resource = "*"`(Cost Explorer API 자체의 제약, 계정 전체 대상 조회라 스코프를 더 좁힐 수 없음) + `sns:Publish`(alerts 토픽 ARN만).
- **메시지:** `{"kind": "custom", "title": "💰 어제 AWS 사용 비용", "body": "YYYY-MM-DD 사용 비용: X.XXXX USD"}`.

### 17.2 콘솔 로그인 알림 (`login_notifier`)

- **왜 알람이 아니라 로그 구독 필터인가:** CloudWatch 알람은 메트릭 값(숫자)만 다뤄서 "누가 로그인했는지"(사용자명)를 실어 나를 수 없다. 반면 **CloudWatch Logs 구독 필터(subscription filter)**는 매칭된 로그 이벤트 원본을 그대로 Lambda에 전달하므로, CloudTrail의 `ConsoleLogin` 레코드에 있는 `userIdentity.userName`을 직접 뽑아낼 수 있다.
- **배관:** 기존 `aws_cloudwatch_log_group.cloudtrail`(§10, 이미 CloudTrail→CloudWatch Logs로 흐르고 있음)을 **그대로 구독** — 신규 CloudTrail 설정 불필요. `aws_cloudwatch_log_subscription_filter.login_notifier`의 `filter_pattern = "{ $.eventName = \"ConsoleLogin\" }"`이 로그인 이벤트만 걸러 `login_notifier` Lambda를 invoke.
- **사용자명 추출 로직**(`lambda_src/login_notifier.py` `_extract_user`): `userIdentity.type == "Root"`면 `"root"`, IAM 사용자면 `userIdentity.userName`(예: `jw_kim`), SSO/federated·assumed-role이면 `userIdentity.arn`의 마지막 세그먼트로 폴백.
- **로그인 성공/실패 둘 다 알림** — `responseElements.ConsoleLogin`(`Success`/`Failure`)을 그대로 보여줌(실패 로그인 시도도 보안상 알아야 할 정보라 필터링하지 않음).
- **권한:** `aws_lambda_permission.cwl_invoke_login_notifier`가 `logs.${var.region}.amazonaws.com`에 invoke를 허용(source_arn = CloudTrail 로그그룹 ARN + `:*`) — Logs 구독 필터가 Lambda를 목적지로 쓸 때는 별도 IAM role 불필요, 이 리소스 기반 권한만 있으면 된다.
- **메시지:** `{"kind": "custom", "title": "🔐 AWS 콘솔 로그인 감지", "body": "사용자: jw_kim\n결과: ✅ Success\nIP: ...\n시각(UTC): ..."}`.

### 17.3 `teams_notifier.py` 확장

기존 `_to_teams_card()`는 CloudWatch 알람 JSON(`AlarmName`/`NewStateValue`/`NewStateReason`)만 가정했다 — 위 두 Lambda가 발행하는 커스텀 메시지(`{"kind": "custom", "title", "body"}`)는 이 shape이 아니므로, `kind == "custom"`이면 알람 파싱을 건너뛰고 title+body를 바로 카드 텍스트로 만들도록 분기 추가(기존 알람 처리 경로는 완전히 무변경).

### 17.4 검증

`terraform fmt`(변경 없음) + `terraform validate` 통과 + `python -m py_compile`(3개 Lambda 파일) 통과. **실 apply·실 로그인/비용 발생 검증은 아직 안 함** — 다음 apply 세션에서: ① `daily_cost_notifier`를 콘솔에서 수동 1회 Invoke(스케줄 대기 없이 테스트) ② 아무 IAM 사용자로 AWS 콘솔 로그인해서 Teams 알림 도착 확인.
