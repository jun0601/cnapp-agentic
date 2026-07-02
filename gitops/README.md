# gitops/ — CD(ArgoCD) + 오토스케일링 선언형 설정

> **한 줄:** CI(코드쪽, GitHub Actions, `$0`)와 분리된 **CD(배포)·노드/파드 오토스케일링**의 *선언형 코드*.
> Git이 '원하는 상태'의 단일 진실이고, ArgoCD가 살아있는 EKS로 pull-sync 한다.
> **apply는 EKS가 살아있는 데모/테스트 세션에서만**(준형과 함께). 안 쓸 땐 destroy — 비용 규율.

---

## 왜 CI / CD를 나눴나

| | 무엇 | 언제 | 비용 |
|---|---|---|---|
| **CI** (`.github/workflows/ci.yml`) | 코드 회귀(run_demo·run_e2e·validate) + Shift-Left 스캔(Trivy·Checkov) | 매 push·PR | **$0** (GitHub Actions, 인프라 무관) |
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

- **파드층 = HPA** (`autoscaling/hpa.yaml`): replica 수를 CPU 부하로 조절. metrics-server 필요.
- **노드층 = Karpenter** (`autoscaling/karpenter.yaml`, Cluster Autoscaler 대체):
  - **spot 우선** + 인스턴스 타입 유연 → 가장 싼 조합 자동 선택(~70% 할인).
  - **consolidation** → 놀거나 저활용된 노드를 자동 정리·교체(CAS엔 없는 절감 레버).
  - 작은 인스턴스부터, `limits.cpu`로 폭주 상한(비용 가드).
- **정직한 핵심:** 데모 규모(파드 소수)에선 노드 오토스케일러 선택이 실비를 크게 좌우하지 않는다.
  진짜 비용 1위 = **EKS control plane ~$0.10/h 고정**(노드 수 무관) → **destroy만이 답**.
  즉 Karpenter를 고른 이유는 *실 절감보다* **모던 아키텍처 + 포폴 신호**이고,
  실제 절감은 **(a) 안 쓸 때 destroy (b) spot** 이 지배적. (상세: [../docs/cost-strategy.md](../docs/cost-strategy.md))

## 부트스트랩 순서 (EKS 살아있을 때)

```
0. infra/shared apply — EKS + Karpenter 컨트롤러(helm)+IRSA + spot 중단 SQS,
   subnet/SG에 karpenter.sh/discovery=cnapp-eks 태그, 작은 시스템 노드그룹(Karpenter/컨트롤러용)
1. ArgoCD 설치:   kubectl create namespace argocd
                  kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
2. 오토스케일링:  kubectl apply -f gitops/autoscaling/karpenter.yaml   # NodePool·EC2NodeClass
                  kubectl apply -f gitops/autoscaling/hpa.yaml         # (metrics-server 먼저)
3. 앱 CD:        kubectl apply -f gitops/argocd/app-target.yaml       # ArgoCD가 apps/target sync
   (product 이미지는 ECR push + ACCOUNT_ID 치환 후 정상 배포)
4. 테스트/데모 후: ArgoCD App 삭제 → infra destroy (비용 규율)
```

## 폴더

```
gitops/
├── README.md                     이 문서(CD·오토스케일링 개념·근거·부트스트랩)
├── argocd/
│   └── app-target.yaml           ArgoCD Application — shop 타깃 앱(pull-sync·self-heal·prune)
└── autoscaling/
    ├── karpenter.yaml            NodePool + EC2NodeClass (spot·consolidation·상한)
    └── hpa.yaml                  member·product HPA (파드층)
```
