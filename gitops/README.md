# gitops/ — CD(ArgoCD) + 오토스케일링 선언형 설정

> **한 줄:** CI(코드쪽, GitHub Actions, `$0`)와 분리된 **CD(배포)·노드/파드 오토스케일링**의 *선언형 코드*.
> Git이 '원하는 상태'의 단일 진실이고, ArgoCD가 살아있는 EKS로 pull-sync 한다.
> **apply는 EKS가 살아있는 데모/테스트 세션에서만**(준형과 함께). 안 쓸 땐 destroy — 비용 규율.

---

## 왜 CI / CD를 나눴나

| | 무엇 | 언제 | 비용 |
|---|---|---|---|
| **CI** (`.github/workflows/ci.yml`) | 코드 회귀(run_demo·run_e2e·validate) + Shift-Left 스캔(Trivy·Checkov) | **PR(→main)·수동**(2026-07-04, main 직접 push엔 미실행 — 노이즈 감소) | **$0** (GitHub Actions, 인프라 무관) |
| **CD** (이 폴더, ArgoCD) | Git 매니페스트 → EKS 배포·동기화·self-heal | EKS 살아있을 때 | EKS 시간과금(데모 세션만) |

- **CI는 항상 켜져 있어도 공짜** → 2인 병렬 회귀 방지 + Shift-Left(차별점)를 상시 증명.
- **CD는 살아있는 클러스터가 필요** → `apply → 데모/테스트 → destroy` 사이클로만(상시 방치 X).

## 왜 ArgoCD (CD 선택 근거)

- **GitOps 업계 표준** — Git이 SSOT, pull 기반 동기화. 포폴 신호 최강(MSP/클라우드팀 표준).
- **pull 기반 보안** — 클러스터가 Git을 *당김* → CI에 클러스터 자격증명을 밀어넣지 않음(키리스/최소권한 테마 정합).
- **self-heal(드리프트 자동 복구)** — 수동 `kubectl` 변경을 Git 상태로 되돌림 → project-draft §19 #3 드리프트 스토리와 연결.
- **데모 친화** — ArgoCD UI에서 "Git push → 자동 sync" 시연이 그림이 좋음.
- **공급망 훅(보너스 D17)** — cosign 서명 이미지만 배포 강제 가능(미서명 거부).
- 대안: Flux(경량·UI 없음 → 시연력 약함), GitHub Actions push(GitOps 아님·드리프트 교정 없음·클러스터 키 필요). → 이 프로젝트엔 ArgoCD.

## 오토스케일링 (2층) — 비용 최적화 근거

- **파드층 = HPA** (`autoscaling/hpa.yaml`): replica 수를 CPU 부하로 조절. metrics-server 필요. → 이 층만 gitops(kubectl/ArgoCD)로 적용.
- **노드층 = Karpenter** (Cluster Autoscaler 대체): **컨트롤러(helm) + NodePool + EC2NodeClass 전부 `infra/karpenter` terraform 레이어가 소유**(2026-07-03 이전). 왜 gitops가 아니라 terraform?
  - Karpenter는 컨트롤러 helm 릴리스 + IAM(IRSA·노드역할·spot 중단 SQS)가 한 몸이라, IAM을 terraform이 만들면서 CRD를 kubectl로 따로 적용하면 소스가 갈린다 → terraform `kubectl_manifest`로 한 레이어에 묶어 apply/destroy 수명주기를 통일.
  - **spot 우선 + on-demand 폴백**(스팟 회수·부족 시 자동 폴백 → 서비스 연속성) + `consolidation`(유휴 노드 자동 정리, CAS엔 없는 절감) + `limits.cpu` 상한. ⚠️ 프리티어라 NodePool을 **t3.small/t3.micro**로 제한(그 밖 타입 RunInstances 거부, 폴백도 이 범위). 용량 전략 근거·2-pool 미분리 판단 = [infra/karpenter/README §2.1](../infra/karpenter/README.md#21-용량-전략-spot-우선--on-demand-폴백).
  - 상세·근거 = [`infra/karpenter/main.tf`](../infra/karpenter/main.tf) 헤더 + [infra/README §2](../infra/README.md).
- **스팟 회수 복원력 (파드층)** (`autoscaling/pdb.yaml` + 타깃 앱 Deployment): 노드가 스팟 회수/consolidation으로 사라질 때 같은 앱 파드가 동시에 다 죽지 않도록 — **PodDisruptionBudget(minAvailable 1)** + **topologySpreadConstraints(maxSkew 1, 노드 분산)** + **replicas 2**를 세트로 배선. 셋이 반드시 함께여야 실효(replica 1이면 PDB가 드레인을 오히려 막고, spread 없으면 한 노드에 몰려 동시 다운). `ScheduleAnyway`라 노드가 1개뿐이어도 스케줄은 안 막음(강제 노드 증설 방지 = 비용).
- **정직한 핵심:** 데모 규모(파드 소수)에선 노드 오토스케일러 선택이 실비를 크게 좌우하지 않는다.
  진짜 비용 1위 = **EKS control plane ~$0.10/h 고정**(노드 수 무관) → **destroy만이 답**.
  즉 Karpenter를 고른 이유는 *실 절감보다* **모던 아키텍처 + 포폴 신호**이고,
  실제 절감은 **(a) 안 쓸 때 destroy (b) spot** 이 지배적. (상세: [../docs/cost-strategy.md](../docs/cost-strategy.md))

## 부트스트랩 순서 (EKS 살아있을 때)

```
0. infra/shared apply — EKS + 작은 관리형 노드그룹(시스템·컨트롤러 파드용) + subnet/SG에
                        karpenter.sh/discovery=cnapp-agentic-shared 태그
0.5 infra/karpenter apply — Karpenter 컨트롤러(helm)+IRSA + spot 중단 SQS + NodePool·EC2NodeClass
   (= './infra/deploy.ps1 -Action apply -Layer karpenter'. NodePool/EC2NodeClass는 여기서 kubectl_manifest로 적용 → gitops 불필요)
1. ArgoCD 설치:   kubectl create namespace argocd
                  kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
2. 파드 오토스케일: kubectl apply -f gitops/autoscaling/hpa.yaml -f gitops/autoscaling/pdb.yaml  # (metrics-server 먼저). 노드층 Karpenter는 0.5에서 이미 적용됨. PDB=스팟 회수 복원력
3. 앱 CD:        kubectl apply -f gitops/argocd/app-target.yaml       # ArgoCD가 apps/target sync
   (product 이미지는 ECR push + ACCOUNT_ID 치환 후 정상 배포)
4. 관측 CD:      kubectl apply -f gitops/argocd/app-monitoring.yaml   # ArgoCD가 kube-prometheus-stack 배포
   (전제: infra/monitoring apply 완료 — Grafana IRSA 역할이 values 파일에 이미 반영돼 있음)
5. 테스트/데모 후: ArgoCD App 삭제 → infra destroy (비용 규율, './infra/deploy.ps1 -Action destroy')
```

## 폴더

```
gitops/
├── README.md                     이 문서(CD·오토스케일링 개념·근거·부트스트랩)
├── argocd/
│   ├── app-target.yaml           ArgoCD Application — shop 타깃 앱(pull-sync·self-heal·prune)
│   └── app-monitoring.yaml       ArgoCD Application — kube-prometheus-stack(3-소스: 공식 차트+이 레포 values+PreSync훅)
├── monitoring/
│   ├── kube-prometheus-stack-values.yaml   Grafana IRSA(CloudWatch 추가 데이터소스, uid 고정)+kube-state-metrics 노드 라벨 허용+리소스 축소 오버라이드
│   ├── presync/
│   │   └── prometheus-crds-job.yaml        PreSync 훅 — CRD를 Helm 본 배포보다 먼저 설치(아래 함정 참고)
│   └── dashboards/                         Grafana 대시보드 4종 — 분야별(아래 §"분야별 대시보드" 참고)
│       ├── cnapp-eks-dashboard.yaml         EKS 개요(노드·파드·CPU·메모리·재시작)
│       ├── cnapp-application-dashboard.yaml 애플리케이션(Lambda 6종·ALB·Cognito·CloudFront)
│       ├── cnapp-infra-dashboard.yaml       인프라(RDS·SQS·Step Functions·S3 감사버킷)
│       └── cnapp-ai-dashboard.yaml          AI/엔진(Bedrock·엔진 EMF 전종)
└── autoscaling/
    ├── hpa.yaml                  member·product·order HPA (파드층, CPU 70%, minReplicas 2)
    └── pdb.yaml                  member·product·order PodDisruptionBudget (스팟 회수 복원력, minAvailable 1)
                                  ※ 노드층 Karpenter(NodePool·EC2NodeClass)는 infra/karpenter terraform 레이어(2026-07-03)
```

**app-monitoring.yaml은 app-target.yaml과 소스 구조가 다르다** — app-target은 "이 레포 = 원본 K8s 매니페스트"이지만, app-monitoring은 "이 레포 = Helm values+`gitops/monitoring/` 하위 매니페스트, 차트 본체는 공식 `prometheus-community` 리포"인 **3-소스 Application**(ArgoCD 2.6+ 기능, `$values` 참조로 소스를 묶음. 소스③은 `path: gitops/monitoring` + `directory.recurse: true`로 `presync/`·`dashboards/`를 한 번에 잡되 `kube-prometheus-stack-values.yaml`은 K8s 리소스가 아니라 `exclude`). `grafana_irsa_role_arn`(IAM 역할 이름이 고정값이라 apply→destroy를 반복해도 안 바뀜, `infra/monitoring/README.md` §참고)이 values 파일에 이미 하드코딩돼 있어 재apply 때마다 값을 다시 쓸 필요가 없다.

### 📊 분야별 대시보드 — EKS + AWS 인프라 **전체**를 Grafana에서

기본으로 딸려오는 kube-prometheus-stack 대시보드 27개는 전부 **"쿠버네티스 클러스터 자체가 건강한가"**(노드·파드·네트워킹)만 본다 — "우리 CNAPP 서비스가 잘 도는가"(Lambda·RDS·SQS·Bedrock·엔진 EMF)는 안 보여준다. 그건 원래 `infra/monitoring`이 만드는 **AWS 네이티브 CloudWatch 대시보드**(24위젯, AWS 콘솔에서 별도로 봄, `terraform output dashboard_url`)의 몫이었다.

CloudWatch가 이미 데이터소스로 연결돼 있으니(§IRSA 배선), 그 24위젯과 **동등한 커버리지**를 Grafana 쪽에도 만들었다 — 한 화면에 다 몰아넣지 않고 **분야별 대시보드 4개**로 나눴다(전환이 쉽고 각자 화면이 덜 복잡함):

| 대시보드 | 패널 | 데이터소스 |
|---|---|---|
| **EKS 개요** | 노드/파드/비정상파드/네임스페이스 수 → 노드별 CPU·메모리 → 파드별 CPU·메모리 top10 → 노드별 파드 개수(bin-packing)·비정상 파드 목록 → 네임스페이스별 재시작 횟수(이 순서로 배치) | Prometheus |
| **애플리케이션** | Lambda 6종(호출·에러·쓰로틀·지연) 개별 패널, ALB(요청·지연·5xx), Cognito(로그인), CloudFront(요청·4xx·5xx) | CloudWatch |
| **인프라(데이터·메시징)** | RDS(CPU·연결·스토리지·IOPS), SQS(큐 깊이·DLQ·백로그 나이), Step Functions(remediation 실행 결과), S3 감사버킷(객체수·크기) | CloudWatch |
| **AI(Bedrock·엔진)** | Bedrock(호출·지연·에러·토큰·추정비용), 엔진 EMF 전종(트리아지 게이트·tool-use·확신도·판정시간·판정분포·케이스별토큰·tool별breakdown) | CloudWatch |

→ **AWS CloudWatch 24위젯과 1:1 대응**(ALB·Step Functions·S3·Cognito·CloudFront까지 전부 포함) — Grafana에서 EKS 안팎을 모두 볼 수 있다는 처음 목표를 충족한다.

**노드 이름 식별 문제**: node-exporter의 `instance` 레이블은 `10.20.10.205:9100`처럼 IP:port라 노드끼리 구분이 안 된다. **AWS EKS는 애초에 노드명 자체가 EC2 프라이빗 DNS(`ip-x-x-x-x...compute.internal`)라 "더 예쁜 이름"이 따로 없다**(EC2 Name 태그도 확인해봤지만 관리형 노드그룹 인스턴스들이 전부 같은 값이라 구분에 무용). 대신 **"이 노드가 상시 관리형 노드그룹(baseline)인지 Karpenter가 띄운 스팟(spot)인지"**가 실질적으로 더 유용한 구분이라 이걸 범례에 얹었다:
1. `kube_node_info`의 `internal_ip`로 join → 실제 노드명(`node`) + `provider_id`에서 정규식으로 뽑은 가용영역(`az`)
2. `kube_node_labels`와 `node`로 join → `eks.amazonaws.com/nodegroup`(관리형)·`karpenter.sh/capacity-type`(스팟) — 이 라벨들은 kube-state-metrics 기본 설정이 카디널리티 보호로 노출 안 해서, `kube-prometheus-stack-values.yaml`에 `kube-state-metrics.metricLabelsAllowlist`로 명시적으로 허용해둬야 값이 채워진다(안 하면 `kube_node_labels` 메트릭은 나오는데 라벨 필드가 빈 채로 나옴).

범례 = `{{short_node}} ({{label_eks_amazonaws_com_nodegroup}}{{label_karpenter_sh_capacity_type}}, {{az}})` → 예: `ip-10-20-11-123 (baseline, ap-northeast-2a)` / `ip-10-20-10-80 (spot, ap-northeast-2a)`.

**동작 원리**: kube-prometheus-stack 차트의 Grafana sidecar가 `grafana_dashboard: "1"` 라벨이 붙은 ConfigMap을 자동으로 찾아 로드한다(기본 대시보드 27개도 이 방식) — 이 ConfigMap 4개도 똑같은 라벨을 달아서 **수동 클릭 없이 자동 등록**되게 했다. `kube-prometheus-stack-values.yaml`의 CloudWatch 데이터소스에 `uid: cloudwatch-monitoring`을 **고정**해둔 이유가 이거다 — uid를 안 고정하면 apply할 때마다 랜덤값이 나와서 대시보드 JSON이 참조하는 datasource uid가 매번 깨진다.

**⚠️ 유지보수 주의 — 비고정 AWS 리소스 ID 3종**: `ALB ARN suffix`(`app-application-dashboard.yaml`)·`Cognito User Pool ID`·`CloudFront Distribution ID`는 Lambda/RDS/IAM 역할처럼 이름이 고정되지 않고 **매 apply마다 AWS가 새로 발급**한다 — `infra/console`을 destroy→재apply하면 이 3개 값이 바뀌어서 해당 CloudWatch 패널이 데이터를 못 찾는다(에러는 안 나고 "No data"만 뜸). 재apply 후 `terraform output`(alb_arn_suffix·cognito_user_pool_id·cloudfront_distribution_id)으로 새 값을 확인해 `cnapp-application-dashboard.yaml`의 세 상수를 갱신할 것. Lambda 함수명·RDS 식별자·SQS 큐 이름·SFN ARN·감사 버킷명은 전부 `${project}-...` 고정 패턴이라 이 문제가 없다.

**검증(2026-07-06)**: Grafana `/api/dashboards/db`+`/api/ds/query`로 4개 대시보드·31개 패널을 전부 임시 등록해 실데이터 확인(28개 실값, 3개는 최근 활동 없어 정상 empty — Cognito 로그인·Step Functions 실행·S3 감사기록) → CloudWatch metric math(비용 계산) 쿼리는 `statistic` 필드 누락(500) → `id` 필드가 대문자로 시작(CloudWatch `Id` 규칙 위반, 400) 두 버그를 잡음 → wildcard 분포 패널(판정분포·tool별breakdown)은 `dimensions` 값이 빈 문자열이 아니라 `["*"]` 배열이어야 함을 확인 → 전부 고친 뒤 ConfigMap으로 옮겨 sidecar 자동 로드까지 재확인.

### ⚠️ 함정 — kube-prometheus-stack 최초 배포 시 Prometheus가 안 뜨는 문제(해결됨)

**증상**: `app-monitoring` sync는 되는데 Grafana만 뜨고 Prometheus는 영원히 `OutOfSync`로 남는다(에러도 안 보임).

**원인 2단(둘 다 실측 확인, troubleshooting.md 2026-07-06 참고)**:
1. `alertmanagers`·`prometheusagents`·`prometheuses`·`thanosrulers` CRD 4종은 OpenAPI 스키마가 커서 일반 `kubectl apply`(annotation 기반)의 262144바이트 제한을 넘어 생성 자체가 실패한다 — `ServerSideApply=true` syncOption만으론 이 4종의 **최초 생성**은 못 고친다.
2. CRD를 먼저 설치해도, `kube-prometheus-stack-operator` 파드가 "CRD 없음" 상태로 이미 떠버리면 그 사실을 내부에 캐싱해버려서 CRD가 나중에 생겨도 영원히 재확인을 안 한다(operator 재시작 전까지 조용히 멈춤).

**해결(이미 반영됨, 손댈 필요 없음)**: `gitops/monitoring/presync/prometheus-crds-job.yaml`이 ArgoCD **PreSync 훅**으로 Helm 차트 본 리소스(=operator 포함)보다 **먼저** 공식 CRD 전용 릴리스 자산을 `kubectl apply --server-side`로 설치한다 — operator가 뜰 때 CRD가 이미 존재해서 위 두 문제가 애초에 안 생긴다. 훅은 `hook-delete-policy: HookSucceeded`로 자기정리되므로 클러스터에 흔적이 안 남는다.

**⚠️ 유지보수 시 주의**: `prometheus-crds-job.yaml`이 받는 CRD 버전(현재 `v0.75.2`)은 `kube-prometheus-stack-values.yaml`이 참조하는 차트(`app-monitoring.yaml`의 `targetRevision`, 현재 `61.9.0`)가 내부적으로 고정하는 prometheus-operator 버전과 **반드시 일치**해야 한다 — 안 맞으면 기능은 되지만 ArgoCD가 계속 `OutOfSync`로 남는다(2026-07-06 실측). 차트 버전을 올릴 땐 `kubectl logs -n monitoring deploy/kube-prometheus-stack-operator | grep "Starting Prometheus Operator"`로 실제 버전을 확인하고 Job의 URL도 같이 갱신할 것.
