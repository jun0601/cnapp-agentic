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
│   ├── kube-prometheus-stack-values.yaml   Grafana IRSA(CloudWatch 추가 데이터소스, uid 고정)+리소스 축소 오버라이드
│   ├── presync/
│   │   └── prometheus-crds-job.yaml        PreSync 훅 — CRD를 Helm 본 배포보다 먼저 설치(아래 함정 참고)
│   └── dashboards/
│       └── cnapp-integrated-dashboard.yaml Grafana 대시보드 — EKS+AWS 인프라 통합 뷰(아래 §"통합 대시보드" 참고)
└── autoscaling/
    ├── hpa.yaml                  member·product·order HPA (파드층, CPU 70%, minReplicas 2)
    └── pdb.yaml                  member·product·order PodDisruptionBudget (스팟 회수 복원력, minAvailable 1)
                                  ※ 노드층 Karpenter(NodePool·EC2NodeClass)는 infra/karpenter terraform 레이어(2026-07-03)
```

**app-monitoring.yaml은 app-target.yaml과 소스 구조가 다르다** — app-target은 "이 레포 = 원본 K8s 매니페스트"이지만, app-monitoring은 "이 레포 = Helm values+`gitops/monitoring/` 하위 매니페스트, 차트 본체는 공식 `prometheus-community` 리포"인 **3-소스 Application**(ArgoCD 2.6+ 기능, `$values` 참조로 소스를 묶음. 소스③은 `path: gitops/monitoring` + `directory.recurse: true`로 `presync/`·`dashboards/`를 한 번에 잡되 `kube-prometheus-stack-values.yaml`은 K8s 리소스가 아니라 `exclude`). `grafana_irsa_role_arn`(IAM 역할 이름이 고정값이라 apply→destroy를 반복해도 안 바뀜, `infra/monitoring/README.md` §참고)이 values 파일에 이미 하드코딩돼 있어 재apply 때마다 값을 다시 쓸 필요가 없다.

### 📊 통합 대시보드 — EKS + AWS 인프라를 Grafana 한 화면에

기본으로 딸려오는 kube-prometheus-stack 대시보드 27개는 전부 **"쿠버네티스 클러스터 자체가 건강한가"**(노드·파드·네트워킹)만 본다 — "우리 CNAPP 서비스가 잘 도는가"(Lambda·RDS·SQS·Bedrock·엔진 EMF)는 안 보여준다. 그건 원래 `infra/monitoring`이 만드는 **AWS 네이티브 CloudWatch 대시보드**(24위젯, AWS 콘솔에서 별도로 봄, `terraform output dashboard_url`)의 몫이었다.

`gitops/monitoring/dashboards/cnapp-integrated-dashboard.yaml`이 이 둘을 **Grafana 한 화면**으로 합친다 — CloudWatch가 이미 데이터소스로 연결돼 있으니(§IRSA 배선) Prometheus 패널과 CloudWatch 패널을 같은 대시보드에 나란히 배치하면 된다:

| 구역 | 패널 | 데이터소스 |
|---|---|---|
| EKS 한눈에 | 노드 수·파드 수·비정상 파드 수·네임스페이스 수 | Prometheus |
| EKS 리소스 | 노드별 CPU/메모리 사용률 | Prometheus |
| Lambda | 호출 수·에러(6종 함수) | CloudWatch |
| RDS/SQS | CPU·연결 수 / 큐 깊이 | CloudWatch |
| AI | Bedrock 호출 수 · 엔진 트리아지 게이트(EMF) | CloudWatch |

**동작 원리**: kube-prometheus-stack 차트의 Grafana sidecar가 `grafana_dashboard: "1"` 라벨이 붙은 ConfigMap을 자동으로 찾아 로드한다(기본 대시보드 27개도 이 방식) — 이 ConfigMap도 똑같은 라벨을 달아서 **수동 클릭 없이 자동 등록**되게 했다. `kube-prometheus-stack-values.yaml`의 CloudWatch 데이터소스에 `uid: cloudwatch-monitoring`을 **고정**해둔 이유가 이거다 — uid를 안 고정하면 apply할 때마다 랜덤값이 나와서 이 대시보드 JSON이 참조하는 datasource uid가 매번 깨진다.

**검증(2026-07-06)**: Grafana API로 대시보드 JSON을 먼저 임시 등록해 패널 12개가 실제 데이터를 반환하는지 확인(`count(kube_node_info)`=3, Lambda `cnapp-agentic-ingest` Invocations 실값 확인) → 검증 후 ConfigMap으로 옮겨 sidecar 자동 로드까지 재확인.

### ⚠️ 함정 — kube-prometheus-stack 최초 배포 시 Prometheus가 안 뜨는 문제(해결됨)

**증상**: `app-monitoring` sync는 되는데 Grafana만 뜨고 Prometheus는 영원히 `OutOfSync`로 남는다(에러도 안 보임).

**원인 2단(둘 다 실측 확인, troubleshooting.md 2026-07-06 참고)**:
1. `alertmanagers`·`prometheusagents`·`prometheuses`·`thanosrulers` CRD 4종은 OpenAPI 스키마가 커서 일반 `kubectl apply`(annotation 기반)의 262144바이트 제한을 넘어 생성 자체가 실패한다 — `ServerSideApply=true` syncOption만으론 이 4종의 **최초 생성**은 못 고친다.
2. CRD를 먼저 설치해도, `kube-prometheus-stack-operator` 파드가 "CRD 없음" 상태로 이미 떠버리면 그 사실을 내부에 캐싱해버려서 CRD가 나중에 생겨도 영원히 재확인을 안 한다(operator 재시작 전까지 조용히 멈춤).

**해결(이미 반영됨, 손댈 필요 없음)**: `gitops/monitoring/presync/prometheus-crds-job.yaml`이 ArgoCD **PreSync 훅**으로 Helm 차트 본 리소스(=operator 포함)보다 **먼저** 공식 CRD 전용 릴리스 자산을 `kubectl apply --server-side`로 설치한다 — operator가 뜰 때 CRD가 이미 존재해서 위 두 문제가 애초에 안 생긴다. 훅은 `hook-delete-policy: HookSucceeded`로 자기정리되므로 클러스터에 흔적이 안 남는다.

**⚠️ 유지보수 시 주의**: `prometheus-crds-job.yaml`이 받는 CRD 버전(현재 `v0.75.2`)은 `kube-prometheus-stack-values.yaml`이 참조하는 차트(`app-monitoring.yaml`의 `targetRevision`, 현재 `61.9.0`)가 내부적으로 고정하는 prometheus-operator 버전과 **반드시 일치**해야 한다 — 안 맞으면 기능은 되지만 ArgoCD가 계속 `OutOfSync`로 남는다(2026-07-06 실측). 차트 버전을 올릴 땐 `kubectl logs -n monitoring deploy/kube-prometheus-stack-operator | grep "Starting Prometheus Operator"`로 실제 버전을 확인하고 Job의 URL도 같이 갱신할 것.
