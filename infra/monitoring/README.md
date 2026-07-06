# infra/monitoring — 운영 관측 (진우 담당)

> CLAUDE §5 "모니터링·관제·추적(Grafana·CloudTrail)" 코드화. **shared·backend·console** 다음 레이어(전부 remote_state로 참조만, 아무것도 안 만듦).
> 보안 findings 대시보드(관제 **앱**, `apps/console`, 준형)와는 다른 것 — 이건 "우리 플랫폼 자체가 잘 돌고 있나"를 보는 운영 **관측**이다.

| | 관제 **앱** (`apps/console`) | 운영 **관측** (`infra/monitoring`, 이 폴더) |
|---|---|---|
| 보는 것 | 보안 findings·attack-path·case | 플랫폼 헬스(가동·지연·에러·비용) |
| 사용자 | 보안 담당자(viewer/approver) | 우리 둘(운영자) |
| 데이터 소스 | RDS(findings 등) | Prometheus + CloudWatch |

---

## 1. 설계 — 하이브리드 3축

플랫폼이 **EKS 안**(타깃 앱 파드)과 **EKS 밖**(Lambda·RDS·SQS·ALB·Step Functions·S3·Bedrock)에 걸쳐 있어서, 관측도 두 세계를 하나로 묶는다.

- **EKS 안** → **Prometheus**(`gitops/monitoring/`에 배포된 kube-prometheus-stack). IRSA 불필요(K8s API·파드 네트워크만 사용).
- **EKS 밖** → **CloudWatch**(각 서비스 네이티브 지표 + 엔진 EMF 커스텀 지표).
- **통합** → **Grafana**가 Prometheus를 기본 데이터소스로, 이 레이어가 만드는 **IRSA 역할**로 CloudWatch를 추가 데이터소스로 붙여 한 화면에서 본다.

| 축 | 무엇 | 소스 | 상태 |
|---|---|---|---|
| ① 애플리케이션 | 타깃 앱 파드 + 관제 앱(백엔드·프론트) | Prometheus(파드) + CloudWatch(Lambda·CloudFront·Cognito) | ✅ 완료 |
| ② 인프라 전체 | EKS·RDS·SQS·ALB·Step Functions·S3 | CloudWatch(전부 네이티브 지표) | ✅ 완료 |
| ③ AI(에이전트) | Bedrock 호출·에이전트 행동(tool-use·확신도·판정·비용 귀속) | CloudWatch(Bedrock 네이티브) + **EMF 커스텀 메트릭** | ✅ 완료(계측: `engine/reasoning/orchestrator.py`) |

**AI 축 계측 핵심 아이디어**: `Orchestrator.run()`이 케이스 전체(evidence·reasoning)를 쥔 유일한 지점이라, 여기서 `print(json.dumps({"_aws": {...}}))`(EMF) 한 줄로 CloudWatch 커스텀 메트릭이 코드/인프라 추가 없이 나온다. 무디멘션 총계(알람용) + `Verdict×RiskLevel`/`Tool` 세부분해(대시보드 `SEARCH()`용)를 **하나의 로그 라인으로 동시에 발행**하는 게 트릭(CloudWatch 알람은 `SEARCH()`를 못 쓰기 때문).

**의존·apply 순서**: `infra/shared` → `infra/backend`·`infra/console` → `infra/monitoring`(이 레이어, `data.terraform_remote_state`로 셋을 읽기만 함) → `gitops/monitoring`(Grafana, `grafana_irsa_role_arn` output을 values에 반영) — 역순으로 destroy.

---

## 2. 만든 것 (테라폼 리소스)

| 구분 | 내용 |
|---|---|
| Grafana IRSA | `aws_iam_role.grafana` — CloudWatch/Logs read-only, OIDC federated |
| CloudWatch Dashboard | `aws_cloudwatch_dashboard.platform` — **24위젯**(Lambda 6·인프라 8·Bedrock 2·비용 1·엔진 EMF 6·CloudFront 1), 모델 추가 시 아래 위젯이 자동으로 밀리는 상대좌표(`local.bedrock_rows_end_y`) |
| CloudTrail 연동 | 로그그룹(`/aws/cloudtrail/${project}`) + IAM 역할 — §3 참고 |
| Teams 알림 | SNS·Lambda 3종·시크릿 3개·알람 7종 — §5 참고 |
| 변수 | `log_retention_days`·Bedrock 단가 4종·`bedrock_hourly_cost_alarm_usd`·`rds_connections_alarm_threshold`(`variables.tf`) |

**알람 7종**(전부 알림 피로 방지 — 진짜 조치 필요한 것만, `cnapp-alerts` 채널로):

| 알람 | 조건 | 왜 |
|---|---|---|
| SQS DLQ 적재 | `ingest-dlq` 메시지 > 0 | 정규화 실패 finding = 데이터 유실 위험 |
| Lambda 에러 | 6종 중 아무 Errors > 0 | 파이프라인 끊김 |
| Step Functions 실패 | `remediation` ExecutionsFailed > 0 | HITL 조치 실패를 아무도 모르는 상황 방지 |
| Bedrock 에러 | InvocationClient/ServerErrors > 0 | AI 조사 자체가 멈췄다는 신호 |
| Bedrock 비용 급증 | 토큰×단가(시간당) > `bedrock_hourly_cost_alarm_usd`(기본 $1.0) | 무한루프·비정상 다량 호출 조기 감지(정밀 예산 통제 아님) |
| RDS 연결 포화 | DatabaseConnections > 임계치 | 조용히 장애로 번지기 전에 |
| 트리아지 게이트 0건 지속 | `FindingsEscalated`가 N분간 0인데 `FindingsEvaluated` > 0 | 트리아지가 조용히 다 걸러버리는 회귀 감지 |

---

## 3. 대시보드

두 종류가 있다 — **CloudWatch Dashboard**(이 레이어가 Terraform으로 만듦, EKS 밖 전용) + **Grafana 대시보드 4종**(`gitops/monitoring/dashboards/`, EKS 안 Prometheus 위주지만 CloudWatch도 섞음). 둘은 겹치지 않고 상호보완 — CloudWatch Dashboard는 콘솔에서 Grafana 없이도 바로 보이고, Grafana는 EKS 안(노드·파드)까지 포함해 한 화면에서 본다.

### 3.1 CloudWatch Dashboard (`cnapp-agentic-platform`, 이 레이어 소유)

**24위젯** — Lambda 6종(각 Invocations/Errors/Duration/Throttles) · 인프라 8종(SQS 깊이·DLQ / RDS CPU·연결 / ALB / SQS 백로그나이 / RDS 스토리지·IOPS / Step Functions / S3 감사버킷 / Cognito 로그인) · Bedrock 2종(호출·지연 / 에러·토큰, 모델별) · Bedrock 추정비용 1종 · 엔진 EMF 6종(트리아지 게이트 / tool-use·확신도 / 판정시간 / 판정분포 / 케이스별 토큰 / tool별 breakdown) · CloudFront 1종.

### 3.2 Grafana 대시보드 4종 (`gitops/monitoring/dashboards/`, GitOps 소유 — 이 폴더 밖)

AWS CloudWatch 24위젯과 별개로, **분야별로 나눠서** 만들었다(사용자 요청 — "모든 걸 그라파나에서도 볼 수 있게, 분야별로"). 이 레이어(`infra/monitoring`)가 만든 IRSA·values 배선 위에서 ArgoCD가 배포한다 — 코드는 `gitops/`에 있지만 개념적으로 이 관측 스토리의 일부라 여기 정리한다. 정확한 패널별 PromQL/CloudWatch 쿼리는 [gitops/README.md](../../gitops/README.md) 참고.

| 대시보드 | 패널 수 | 데이터소스 | 커버리지 |
|---|---|---|---|
| **CNAPP - EKS 개요** | 12 | Prometheus | 노드/파드/비정상파드/네임스페이스 수 · 노드별 CPU·메모리(baseline/spot 구분) · 파드별 CPU·메모리 top10 · 노드별 파드개수(bin-packing) · 비정상 파드 목록 · 네임스페이스별 재시작 횟수 |
| **CNAPP - 애플리케이션** | 9 | CloudWatch | Lambda 6종 개별(ingest·normalize·correlation·orchestrator·console-backend·remediation) · ALB · Cognito 로그인 · CloudFront |
| **CNAPP - 인프라(데이터·메시징)** | 6 | CloudWatch | RDS CPU·연결/스토리지·IOPS · SQS 큐 깊이·DLQ/백로그나이 · Step Functions(remediation) · S3 감사버킷 |
| **CNAPP - AI(Bedrock·엔진)** | 9 | CloudWatch | Bedrock 호출·지연/에러·토큰/추정비용 · 엔진 트리아지 게이트·tool-use·확신도·판정시간·판정분포·케이스별 토큰·tool별 호출 |

**EKS 대시보드의 노드 식별 함정**: EKS 노드의 `.metadata.name`은 EC2 프라이빗 DNS(`ip-x-x-x-x...`) 그 자체라 별도의 "친화적 이름"이 K8s API에 없다(EC2 Name 태그도 관리형 노드그룹 내 전부 동일값이라 무용). 대신 **상시 관리형 노드그룹(baseline) vs Karpenter 스팟(spot)** 구분 + 가용영역을 범례에 얹는 것으로 대체(`kube-state-metrics.metricLabelsAllowlist` 필요 — 기본값은 카디널리티 보호로 라벨 값을 비움).

**ArgoCD Application 이름 함정**: 배포 파일명은 `gitops/argocd/app-monitoring.yaml`이지만 실제 `metadata.name`은 **`monitoring`**이다 — `kubectl get application app-monitoring -n argocd`로 조회하면 `NotFound`(진짜로 없는 게 아니라 이름이 다른 것). `kubectl get applications -n argocd`로 목록을 봐야 한다.

---

## 4. CloudTrail → Grafana 연동

**트레일 자체(멀티리전·SSE-S3)는 계속 수동 관리**(`docs/manual-infra.md` §1) — 계정 보안 베이스라인은 이 레이어의 `apply→destroy` 사이클에 절대 휘말리면 안 되기 때문. 이 레이어가 만드는 건 "트레일 → CloudWatch Logs" **배달 경로**뿐(로그그룹 + 트레일이 assume하는 IAM 역할). 기존 트레일(`cnapp-org-trail`)에 이 로그그룹 ARN을 1회 수동 연결(콘솔 또는 `aws cloudtrail update-trail`)해야 완성 — **완료됨**.

Grafana 쪽은 새 위젯 없이 **Logs Insights 쿼리**만으로 "AI 에이전트가 실제로 호출한 API 타임라인"을 볼 수 있다(대상 역할: `cnapp-agentic-engine-orchestrator`).

---

## 5. Teams 알림 — 채널 3개, 각자의 배관

| 채널 | 소스 | 배관 |
|---|---|---|
| `cnapp-alerts` | CloudWatch 알람 7종(§2) | `aws_sns_topic.alerts` → `teams_notifier` Lambda → 전용 시크릿 |
| `cnapp-cost` | `daily_cost_notifier`(EventBridge, 매일 09:00 KST) | SNS 안 거치고 **직접 POST**(전용 시크릿) |
| `cnapp-login` | `login_notifier`(CloudWatch Logs 구독 필터, CloudTrail `ConsoleLogin`) | SNS 안 거치고 **직접 POST**(전용 시크릿) |

**분리 원칙**: 일반 운영 알람은 `cnapp-alerts`가 기본값. 비용·로그인처럼 **보는 사람/노이즈 성격이 뚜렷이 다를 때만** 전용 채널+전용 Power Automate 흐름+전용 Secrets Manager 시크릿을 새로 판다(채널마다 흐름을 손으로 새로 만들어야 해서 비용이 든다 — 남발 금지).

### 5.1 daily_cost_notifier

전날 AWS 사용 비용을 Cost Explorer로 조회해 매일 09:00 KST에 발행. **CloudWatch 알람이 아니라 능동 Lambda**로 만든 이유 — 알람은 "임계값 초과"만 다루는데 이건 "매일 정기 리포트"(항상 보고할 값이 있음) 개념이라 안 맞는다.

- ⚠️ Cost Explorer API 엔드포인트는 계정/Lambda 리전과 무관하게 **us-east-1 고정**(AWS 자체 제약).
- ⚠️ **순액(net)만 보여주면 안 된다** — 이 계정은 프로모션 크레딧이 실사용을 100% 상쇄해서 `UnblendedCost` 그대로 보면 매일 거의 정확히 $0으로 보인다. `GroupBy=RECORD_TYPE`(Usage/Credit)로 쪼개 **실사용·크레딧 상쇄·순액 3줄을 전부** 표시한다 — 크레딧 소진 시 실제로 청구될 금액을 미리 알 수 있게.

### 5.2 login_notifier

CloudTrail `ConsoleLogin` 이벤트를 CloudWatch Logs **구독 필터**로 받아 사용자명과 함께 알림. **CloudWatch 알람이 아니라 로그 구독 필터**를 쓴 이유 — 알람은 메트릭 값(숫자)만 다뤄서 "누가 로그인했는지"를 실어 나를 수 없다.

- 계정 내 **누구든** 로그인하면 잡힌다(IAM 사용자별로 따로 설정할 필요 없음) — `userIdentity.userName`(IAM), `root`, 또는 arn 마지막 세그먼트(SSO/federated)로 사용자 추출.
- 로그인 **성공/실패 둘 다** 알림(실패 시도도 보안상 필요한 정보).
- 시각은 KST로 변환해서 표시(CloudTrail 원본은 UTC).
- ⚠️ 실시간 아님 — 구독 필터 특성상 몇 분 지연될 수 있음(정상 동작).

### 5.3 Power Automate 함정 3가지 (다음에 채널 추가할 때 반드시 참고)

1. **"HTTP 요청이 수신되면"(Request) 트리거 쓰지 말 것** — Premium 커넥터인 데다, **이 테넌트(Default Power Platform 환경)가 모든 수동/HTTP 트리거에 OAuth 인증을 강제**(`DirectApiAuthorizationRequired`). Premium 평가판을 받아도, 새 Developer 환경을 따로 만들어도 동일하게 막힘(테넌트 전역 정책으로 실측 확인). 옛날식 Teams "수신 웹후크(Incoming Webhook)" 커넥터도 이 테넌트에서 완전히 제거됨.
2. **대신 Teams 채널 "···" → "워크플로" → 템플릿 "채널에 웹후크 알림 보내기"로 시작할 것** — 이 공식 템플릿의 트리거("Teams 웹후크 요청이 수신된 경우")만 유일하게 OAuth 없이 서명(`sig=`) 기반 URL을 발급한다.
3. **이 템플릿이 기본으로 만들어주는 "Post card in a chat or channel" 액션은 삭제할 것** — 내부적으로 요청 바디 전체를 `AdaptiveCard.FromJson()`에 그대로 넘겨 파싱을 시도해서, 최상위에 `"type": "AdaptiveCard"`가 없으면 무조건 실패한다. 이중 JSON 인코딩으로 우회를 시도해봤지만 콘텐츠(한글·이모지·마크다운)에 따라 원인 불명으로 불규칙하게 실패 — **신뢰 불가로 결론**. 삭제하고 그 자리에 **"채팅 또는 채널에서 메시지 게시"**(평문, 메시지 필드는 `fx` 식으로 `triggerBody()?['text']`)를 넣는 게 유일하게 안정적인 방법. 평문이어도 Teams가 `**굵게**`·줄바꿈은 렌더링해준다.

### 5.4 웹훅 URL 로테이션 시 주의

과거 `docs/manual-infra.md`에 웹훅 URL이 평문으로 커밋됐다가 유출된 적이 있다(이 레포는 GitHub public). URL 값 자체는 **Secrets Manager에만** 두고 절대 git에 커밋하지 않는다 — Terraform은 시크릿을 생성만 하고 값은 모른다(`recovery_window_in_days=0`, apply/destroy 반복 시 이름 충돌 방지). 값 주입은 항상:

```
aws secretsmanager put-secret-value --secret-id <ARN> --secret-string '<url>'
```

---

## 6. 비용 원칙

- CloudWatch 표준 지표·EMF 커스텀 메트릭 모두 기존 서비스/Lambda 로그에 얹는 것이라 추가 요금 없음.
- Bedrock invocation logging(프롬프트 전문 저장)은 데모 캡처 구간에만 on, 상시 금지.
- Prometheus/Grafana는 EKS가 떠 있는 세션에서만 의미 있음.
- **`daily_cost_notifier`·`login_notifier`·`teams_notifier`는 Lambda+EventBridge+Secrets Manager뿐이라 거의 $0** — EKS/RDS/NAT처럼 비싼 다른 레이어와 달리, 굳이 매일 destroy할 이유가 없다(§7 고려사항 참고).

---

## 7. 남은 것 / 보류 항목

| 항목 | 내용 | 예상 공수 |
|---|---|---|
| **Grafana Postgres 데이터소스** | RDS(`cases`·`findings` 테이블)를 Grafana 3번째 데이터소스로 직접 SQL 조회 — MTTR·tool-use 분포·verdict 히스토그램 등. 이미 EMF로 대부분 커버돼 우선순위 낮음으로 보류. | 읽기전용 롤 추가+적용 20~30분, Grafana 배선(자격증명 안전하게 넣는 게 까다로움) 30~45분, SQL 패널 작성·검증 45~60분 — **총 2~2.5시간** |
| **X-Ray 분산 트레이싱** | `ingest→normalize→correlation→orchestrator` 요청 1건의 전체 경로를 하나의 트레이스로. | 얕게(Lambda 개별 트레이싱만, 경로 안 이어짐): 30~45분. 제대로(SQS·EventBridge 비동기 경계 넘어 컨텍스트 전파, 4개 핸들러 코드 수정): **3.5~4.5시간** |
| **`infra/monitoring`을 상시 유지할지** | 매일 apply/destroy 반복 시 `daily_cost_notifier`의 09:00 스케줄이 인프라 없는 시간대엔 못 울림. 이 레이어는 비싼 리소스가 없어서(§6) destroy 대상에서 빼는 게 실질적 해법 — 구조적으로 완전히 분리하려면 이 레이어에서 알림 3종만 별도의 작은 레이어(`infra/notify`)로 쪼개는 방법도 있음(웹훅 URL 재주입 1회 필요). **고려 사항으로 보류, 아직 미결정.** | — |

---

## 참고

이 문서는 **현재 상태만** 유지한다. 언제·왜·어떻게 바뀌었는지의 상세 이력(버그 수정·재검증·apply 로그)은 [CLAUDE.md 변경 로그](../../CLAUDE.md#변경-로그-최신이-위로)와 [troubleshooting.md](../../troubleshooting.md)(`[infra]` 태그)에서 관리한다.
