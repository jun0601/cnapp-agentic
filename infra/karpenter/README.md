# infra/karpenter — 동적 노드 오토스케일러 (클러스터 런타임 레이어)

> **한 줄:** Karpenter 컨트롤러(helm) + IAM(IRSA·노드역할·spot 중단 SQS) + NodePool/EC2NodeClass(CRD)를
> **한 레이어로 묶어** apply/destroy 수명주기를 통일한다. 2026-07-03 `infra/shared`에서 분리 신설.

---

## 1. 왜 별도 레이어인가 (분리 근거)

- **shared는 '순수 AWS 폴대'여야 한다.** Karpenter가 shared에 있으면 폴대가 helm/kubectl provider(=라이브 EKS 클러스터)에 의존 — 컨트롤러가 안 뜨면 shared 전체 apply가 실패하고, destroy 때 helm state를 수동으로 만져야 했다(2026-07-03 실사고). 분리로 실패·수명주기를 격리.
- **왜 gitops(kubectl/ArgoCD)가 아니라 terraform인가:** Karpenter는 컨트롤러 helm 릴리스 + IAM이 한 몸이다. IAM을 terraform이 만들면서 CRD를 kubectl로 따로 적용하면 소스가 갈린다 → `kubectl_manifest`로 한 레이어에 묶음. (파드층 HPA는 gitops 유지.)

## 2. 배포 리소스

| 구역 | 리소스 | 역할 |
|---|---|---|
| ① 서브모듈 | `module.karpenter`(terraform-aws-modules/eks//modules/karpenter ~>20.24) | 컨트롤러 IRSA 역할 · 노드 IAM 역할/인스턴스프로파일 · spot 중단 SQS+EventBridge |
| ①' 보충 IAM | `aws_iam_role_policy.controller_113_gc` | 모듈 v20 권한셋에 없는 `iam:ListInstanceProfiles`(Karpenter 1.13 GC용, `/karpenter/*` 경로 스코프) |
| ② 컨트롤러 | `helm_release.karpenter`(oci://public.ecr.aws/karpenter, **replicas=1**, wait, timeout 900) | kube-system에 컨트롤러 설치 |
| ③ CRD | `kubectl_manifest.ec2nodeclass`·`nodepool`(둘 다 이름 `cnapp-spot`) | AL2023 · discovery 태그 셀렉터 · **t3.small/t3.micro amd64**(프리티어) · **spot 우선 + on-demand 폴백** · cpu 상한 8 · consolidation 30s · 인스턴스 Name 태그 `…-karpenter-spot` |

의존: `infra/shared`의 `eks_cluster_name`·`eks_oidc_provider_arn`(remote_state) + 라이브 클러스터(`data.aws_eks_cluster`).
노드 발견: shared가 private 서브넷·노드 SG에 붙인 `karpenter.sh/discovery = cnapp-agentic-shared` 태그.

> **이름 규칙:** NodePool·EC2NodeClass·베이스라인 노드그룹에 `default`를 쓰지 않는다(프로젝트 식별). NodePool/EC2NodeClass=`cnapp-spot`, shared 베이스라인 노드그룹=`baseline`, Karpenter 인스턴스 Name 태그=`cnapp-agentic-shared-karpenter-spot`.

## 2.1 용량 전략 (spot 우선 + on-demand 폴백)

NodePool `cnapp-spot`의 `karpenter.sh/capacity-type = ["spot", "on-demand"]`.

- **왜 혼합인가:** "스팟 전용"은 스팟 회수·재고부족 시 파드가 못 뜨는 단일 실패점이다. Karpenter는 항상 더 싼 **spot을 먼저** 시도하고, 스팟을 못 잡거나 회수당하면 **자동으로 on-demand로 폴백**해 서비스 연속성을 지킨다. 스팟이 잘 잡히는 평상시엔 추가비용 0.
- **왜 단일 NodePool인가(2-pool 분리 안 함 — 판단 근거):** 이 데모는 ⓐ 프리티어라 인스턴스가 t3.small/t3.micro(전부 스팟 적격)로 제한되고 ⓑ 워크로드가 전부 stateless(member API + placeholder 파드)다. 따라서 "크리티컬=on-demand 전용 풀"을 따로 둬도 데모에서 실제로 쓰일 일이 없는 **전시용 복잡도**가 된다. 폴백 하나로 실효(연속성)를 다 얻으므로 단일 풀 유지 = 오버엔지니어링 회피.
- **프로덕션이라면:** NodePool을 2개로 분리 — 크리티컬/stateful = **on-demand 풀(weight 낮게)**, stateless = **spot 풀(weight 높게)**. `weight`로 stateless를 스팟에 우선 배치하고 DB·상태저장 워크로드는 on-demand에 고정. 즉 "스팟 남발"이 아니라 **워크로드 성격 기반 배치 + 회수 복원력**이 핵심.
- **프리티어 폴백 비용:** on-demand 폴백도 t3 범위 내 → Karpenter가 폴백 시 free-tier 적격 **t3.micro on-demand(750h/월 무료)**를 우선 선택해 폴백조차 대개 $0. (t3.small on-demand는 유료지만 스팟 부족이 드물어 실사용 희박.)
- **스팟 회수 복원력(파드층):** 노드 회수 시 파드가 동시에 다 죽지 않도록 타깃 앱에 **PodDisruptionBudget(minAvailable 1) + topologySpreadConstraints(노드 분산) + replicas 2**를 세트로 배선(gitops/autoscaling/). 상세는 [gitops/README](../../gitops/README.md).

## 3. apply / destroy (순서는 deploy.ps1이 강제)

```powershell
./infra/deploy.ps1 -Action apply   -Layer karpenter   # 선행: shared apply 완료(라이브 EKS 필요)
./infra/deploy.ps1 -Action destroy -Layer karpenter   # shared destroy '직전'에 — NodePool 삭제→노드 드레인→helm 제거
```

- **apply 순서:** shared **직후**(클러스터·OIDC가 있어야 함). target/backend/console과는 병렬 가능.
- **destroy 순서:** shared **직전**. shared(=EKS)를 먼저 지우면 이 레이어 destroy가 라이브 클러스터·remote_state를 못 읽어 실패하고, Karpenter가 띄운 노드가 고아로 남아 VPC/EKS destroy를 막는다.
- apply 머신 전제: aws CLI + 클러스터 admin 자격(생성자 jh_lee 또는 access entry 등록자) — helm/kubectl provider가 `aws eks get-token`으로 인증.

## 4. 실검증 기록 (2026-07-03 라이브 사이클)

전 과정 실 AWS에서 검증 완료:

1. **컨트롤러 1/1 Ready** (chart 1.13.0)
2. **NodePool·EC2NodeClass READY True** — discovery 태그로 서브넷/SG 발견 성공
3. **노드 프로비저닝**: 1 CPU×3 파드(2노드 용량 초과) → Pending 파드 감지 → **t3.micro 스팟 NodeClaim ~30초 만에 프로비저닝·조인** → 파드 스케줄 (프리티어 제약 준수 확인)
4. **Consolidation**: scale 0 → 30초 후 유휴 노드 자동 회수
5. 최근 로그 ERROR 0

### 4.1 함정 (같은 실수 방지)

- **⚠️ 차트 버전은 '존재'가 아니라 'K8s 호환'을 봐야 한다.** 1.1.1은 존재하지만 K8s 1.34에서 컨트롤러가 시작 즉시 panic(`karpenter version is not compatible with K8s version 1.34`) → CrashLoopBackOff. apply 전 `helm show chart oci://public.ecr.aws/karpenter/karpenter`(최신 확인) + 호환성 매트릭스 확인. 현재 기본값 1.13.0 = K8s 1.34 실검증 완료.
- **⚠️ helm `wait=true`는 '시작 즉시 panic'형 CrashLoop을 못 잡을 수 있다** — 1.1.1 사고 때 helm_release가 성공으로 통과하고 terraform apply도 green이었다(레이어 22개 생성 완료). **terraform green ≠ 컨트롤러 healthy** → apply 후 `kubectl get pods -n kube-system -l app.kubernetes.io/name=karpenter`로 1/1 Running 확인이 필수.
- **⚠️ helm은 upgrade 때 CRD를 안 올린다**(install 때만). 차트 버전을 올려 in-place upgrade하면 CRD가 구버전으로 남아 `unknown field "status.nodes"` 류 경고 발생. fresh apply(destroy→apply)는 무관. in-place 업그레이드 시엔 Karpenter 릴리스의 CRD를 kubectl로 별도 적용.
- **⚠️ 프리티어 계정 제약**: NodePool requirements를 t3.small/t3.micro(amd64)로 제한 — 그 밖 타입은 RunInstances가 `InvalidParameterCombination(Free Tier)`으로 거부됨(NAT 인스턴스에서 실측된 계정 제약과 동일). **on-demand 폴백도 이 타입 범위 내**(폴백 시 free-tier t3.micro on-demand 우선 → 폴백조차 대개 $0).
- 모듈 v20 권한셋은 Karpenter 1.13의 `iam:ListInstanceProfiles`(instance-profile GC)가 빠져 있어 매 리컨실 AccessDenied ERROR — 보충 정책(②' 참조)으로 해소(프로비저닝 자체는 무영향이었음).

## 5. 비용

컨트롤러 파드는 기존 관리형 노드그룹 위에서 돎(추가 노드 0). 실비는 **Karpenter가 띄우는 스팟 노드 사용 시간**뿐(데모 검증 = t3.micro 스팟 몇 분 ≈ $0.001). 진짜 절감 근거·정직한 트레이드오프는 [docs/cost-strategy.md §2.7](../../docs/cost-strategy.md).
