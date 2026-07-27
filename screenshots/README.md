# screenshots — 포폴·README용 실행 증거

각 이미지가 **무엇을 증명하는지**와 **어떻게 다시 찍는지**를 남긴다.
캡처 시점에 실제로 돌아간 화면만 넣는다 — 낡은 샷은 본문 주장을 스스로 반박하므로 즉시 교체한다.

## 목록

| 파일 | 증명하는 것 | 인프라 필요 |
|---|---|---|
| `console/console-dashboard.png` | Secure Score(AWS 35 / Azure 83, 실 RDS 산출) · 공격 경로 3 · 우선순위 finding · 우상단 **실데이터** 배지 | ✅ |
| `console/console-attack-path.png` | 멀티경로 3개(위험도순) · AWS/Azure 레인 분리 · 크로스클라우드 엣지(빨강) · 공격 서사 | ✅ |
| `console/console-findings.png` | findings 목록(실 RDS) | ✅ |
| `console/console-system.png` | AI·시스템 뷰 — 모델·RAG 지식베이스·Bedrock 사용량 | ✅ |
| `console/console-chat.png` | RAG 챗 — Titan 임베딩 → pgvector 검색 → Bedrock 답변 + **근거 4건(control_id 칩)** | ✅ |
| `console/console-evidence-tab.png` | AI 능동조사 — **confirmed** 판정 · 트리아지 게이트 사유 · 가설 · 실 read-only API 호출 증거(`BlockPublicAcls=False` 등) | ✅ |
| `console/console-login.png` | 커스텀 도메인(`cnapp-agentic.cloud`) HTTPS + SSO 진입점 | ✅ |
| `argocd/argocd-shop-target-tree.png` | GitOps 실동작 — `shop-target` Synced/Healthy + 리소스 트리(파드 6개 running 1/1) | ✅ |
| `argocd/argocd-applications-list.png` | Application 4개 전부 Synced/Healthy(타깃 앱뿐 아니라 플랫폼 전체가 GitOps 관리) | ✅ |
| `ci/*.png` | GitHub Actions `ci.yml` 회귀 게이트 통과 | ❌ (인프라 무관) |

> ⚠️ `apps/console/screenshots/`의 옛 이미지는 **쓰지 말 것** — MSW 목업 모드 배지 · 옛 하드코딩 점수(62/74) · 옛 6화면 내비 · 단일 공격경로 상태다. 위 `console/`이 대체본이다.

## ⚠️ 찍기 전에 — 지식베이스 적재 확인 (재apply 직후엔 반드시)

`rag_chunks`는 RDS에 있으므로 **인프라를 destroy→재apply하면 비어 있다.** 비어 있으면
`/chat`이 검색 결과 0건으로 답해서 **근거 없는 답변**이 나오고("RAG · 실 지식베이스" 배지가
사실이 아니게 됨), Evidence 탭의 `rag_refs` 칩도 안 뜬다. 캡처 전에 반드시:

```bash
curl -s https://cnapp-agentic.cloud/api/system   # rag.chunks 가 0이면 아래 적재
python -m rag.corpus.load_live --emit-sql rag_chunks.sql   # 절차는 스크립트가 출력
```

2026-07-21에 실제로 이 상태로 스크린샷을 찍었다가 폐기했다 — 답변은 그럴듯했지만 근거가 0건이었다.

## 다시 찍는 법

### 콘솔 화면 (인프라 살아있을 때)

로그인 게이트 때문에 라이브 SPA는 바로 못 찍는다. **인증을 위조하지 않고** 실데이터를 렌더하려면
OIDC를 아예 구성하지 않은 캡처 전용 빌드를 쓴다.

`apps/console/.env.readme` (gitignore 대상이라 직접 만든다):

```
VITE_USE_MOCK=false
VITE_API_BASE=https://cnapp-agentic.cloud/api
```

```bash
cd apps/console
npx vite build --mode readme --outDir dist-readme
npx vite preview --outDir dist-readme --port 4173
```

- `VITE_USE_MOCK=false` → MSW 끔(목업 배지 안 뜸, 실 API 호출)
- `VITE_COGNITO_*` 미주입 → `oidcConfigured()=false` → 로그인 게이트 없음. **토큰을 위조하는 게 아니라 OIDC를 구성하지 않은 빌드**이며, 역할은 기본 viewer다.
- 백엔드는 무인증 요청을 fail-closed로 viewer 취급하므로 읽기 API는 정상 응답한다.
- 로컬 오리진은 백엔드 CORS 화이트리스트(CloudFront) 밖이라, 캡처용 브라우저만 web security를 끈다.

라우트: `/` · `/findings` · `/findings/:id` · `/attack-paths` · `/chat` · `/system` · `/remediation` · `/compliance` · `/audit`

### ArgoCD

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

`https://localhost:8080` (self-signed 경고 무시) → admin 로그인 → 사이드바 접고 줌 70%로 맞춰야 트리 전체가 들어간다.

## 인프라 터미널 캡처 (PPT 인프라 설계 슬라이드용)

`deploy.ps1` 실행 4컷으로 "순서를 코드로 강제 + 잔존 0"을 동작으로 증명한다. PPT 인프라 설계 슬라이드의 placeholder를 이 4컷으로 교체한다. **인프라를 올렸다 내리는 한 사이클에서 한 번에** 찍는다(콘솔·ArgoCD·X-Ray 캡처와 같은 세션).

**터미널 세팅** — Windows Terminal → PowerShell 탭(VS Code 하단 패널 X · cmd X — `deploy.ps1`은 .ps1이라 PowerShell 필요) · 다크 테마 · 폰트 16pt · 창 넓게(줄바꿈 방지). 시작 전 — PowerShell 기본 실행 정책이 `.ps1`을 막으므로(`UnauthorizedAccess`) **현재 세션만** 허용(창 닫으면 원복, 시스템 영구변경 없음) + 레포 루트로 이동:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
cd F:\@_LEE_JH\AWS_클라우드\개인보안프로젝트\cnapp-agentic
```

apply/destroy는 각각 수십 분 걸리고 로그가 스크롤로 밀린다 — 불안하면 세션 전체를 **화면 녹화**(OBS·Win+G)해두고 프레임을 골라도 된다. (아래 배너·완료줄·훅줄은 전부 `deploy.ps1`이 실제로 찍는 문구다.)

---

#### ① apply 정방향 — 완료 후 캡처
```powershell
.\infra\deploy.ps1 -Action apply -AutoApprove
```
화면에서 볼 것:
- 맨 위 배너(청록): `== terraform apply | order: shared -> karpenter -> target -> backend -> console -> monitoring ==`
- 레이어마다 헤더 `--- [shared] terraform apply ---` … `--- [monitoring] terraform apply ---`
- 각 레이어 끝에 terraform이 찍는 `Apply complete! Resources: N added, 0 changed, 0 destroyed.`
- karpenter 통과줄: `[karpenter] controller healthy (rollout complete)`

**강조(크롭):** ⓐ **order 배너**(순서를 코드가 강제) + ⓑ 6개 레이어의 `Apply complete!`가 위→아래로 이어진 부분을 한 화면에. (`[target] layer vars: -var enable_s3_public=true ...` 줄까지 보이면 "데모 결함을 코드로 켠다"는 근거로 덤.)

#### ② destroy 역방향 — 완료 무렵 캡처
```powershell
.\infra\deploy.ps1 -Action destroy -AutoApprove
```
화면에서 볼 것:
- 배너(청록): `== terraform destroy | order: monitoring -> console -> backend -> target -> karpenter -> shared ==`
- 바로 아래(노랑): `(destroy is reverse: monitoring first -> shared last; Grafana Ingress ALB is auto-released before monitoring destroy)`
- 레이어마다 `Destroy complete! Resources: N destroyed.`

**강조(크롭):** **역방향 order 배너**(apply와 정반대 — monitoring 먼저, shared 마지막) + 노란 설명줄. 이 "역순"이 이 컷의 전부다.

#### ③ 안전 훅 — ②가 도는 **도중** 캡처 (차별점)
②destroy 진행 중 아래 훅 문구가 지나갈 때 잡는다:
- `[karpenter] orphan-node sweep: terminating N leftover Karpenter node(s): i-...`
- `[karpenter] deleting orphaned pod ENI eni-... (was pinning the node SG)`
- `[karpenter] orphan-node sweep: nodes terminated + pod ENIs cleared -> node SG can now delete`
- (monitoring 직전) `[monitoring] Grafana Ingress released (ALB deleted) -- safe to destroy monitoring`

**강조(크롭):** 위 훅 문구 2~3줄. "고아 pod ENI 삭제 → 노드 SG 해제" 또는 "Grafana Ingress 먼저 놔줘 ALB 고아 방지" 중 하나가 보이면 됨. **남들 배포 스크립트엔 없는 방어 로직이라, 인프라 파트의 진짜 한 방이 이 컷이다.**
> 고아 노드가 없던 destroy면 훅이 `[karpenter] orphan-node sweep: none found (controller deprovisioned cleanly)`만 찍는다 — 그럼 Grafana Ingress 줄로 대체.

#### ④ 검증 = 전부 0 — destroy 후 캡처 (★메인픽)
destroy가 끝난 뒤 아래 블록을 그대로 붙여넣고 **그 출력**을 찍는다(전부 `[]`면 잔존 0):

```powershell
$R="ap-northeast-2"
aws eks list-clusters --region $R --query clusters
aws rds describe-db-instances --region $R --query "DBInstances[].DBInstanceIdentifier"
aws ec2 describe-vpcs --region $R --filters "Name=isDefault,Values=false" --query "Vpcs[].VpcId"
aws lambda list-functions --region $R --query "Functions[?starts_with(FunctionName,'cnapp')].FunctionName"
aws elbv2 describe-load-balancers --region $R --query "LoadBalancers[].LoadBalancerName"
```

**강조(크롭):** 명령과 그 아래 `[]` 출력이 나란히 보이게. 하단 문구 "apply→검증→destroy 완주, 잔존 0"을 화면으로 증명하는 컷이다.

> 남는 것 = `tfstate` · `cloudtrail-logs` · `config` S3 버킷 + Route53 (의도된 baseline, ~$0).
> ⚠️ **②③은 한 번의 destroy에서 나온다** — ③(훅)은 진행 중, ②(완료 배너)는 끝 무렵. 놓치면 destroy를 또 돌려야 하니 화면 녹화 권장.

**X-Ray 서비스맵**(`shot-xray-servicemap.png` — 웹 05섹션이 이 파일 없으면 자동 숨김)도 인프라 살아있을 때 같이 찍는다: AWS 콘솔 → X-Ray → 서비스맵(수집 → 정규화 → 상관 → 오케스트레이터 → 조치 5 Lambda).

## 이 방식으로 못 찍는 것

**"실제 SSO 로그인 상태"** — 주소창 `cnapp-agentic.cloud` + 로그인 계정(APPROVER) 배지가 함께 필요한 샷(PPT 슬라이드 7)은
Entra 자격증명으로 **직접 로그인한 뒤** headed 브라우저로 캡처해야 한다(2026-07-07에 쓴 PowerShell `PrintWindow` 방식 —
`page.screenshot`은 브라우저 크롬을 안 담아서 주소창이 안 나온다).

로그인 세션을 흉내 내려고 localStorage에 ID 토큰을 넣는 방법은 **쓰지 않는다** — 프론트가 서명검증을 안 하므로
기술적으론 통과하지만, 일어나지 않은 로그인을 증거처럼 남기는 것이라 포폴에 부적합하다.
