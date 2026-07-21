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
| `console/console-chat.png` | RAG 챗 — Titan 임베딩 → pgvector 검색 → Bedrock 실 답변 | ✅ |
| `console/console-login.png` | 커스텀 도메인(`cnapp-agentic.cloud`) HTTPS + SSO 진입점 | ✅ |
| `argocd/argocd-shop-target-tree.png` | GitOps 실동작 — `shop-target` Synced/Healthy + 리소스 트리(파드 6개 running 1/1) | ✅ |
| `argocd/argocd-applications-list.png` | Application 4개 전부 Synced/Healthy(타깃 앱뿐 아니라 플랫폼 전체가 GitOps 관리) | ✅ |
| `ci/*.png` | GitHub Actions `ci.yml` 회귀 게이트 통과 | ❌ (인프라 무관) |

> ⚠️ `apps/console/screenshots/`의 옛 이미지는 **쓰지 말 것** — MSW 목업 모드 배지 · 옛 하드코딩 점수(62/74) · 옛 6화면 내비 · 단일 공격경로 상태다. 위 `console/`이 대체본이다.

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

## 이 방식으로 못 찍는 것

**"실제 SSO 로그인 상태"** — 주소창 `cnapp-agentic.cloud` + 로그인 계정(APPROVER) 배지가 함께 필요한 샷(PPT 슬라이드 7)은
Entra 자격증명으로 **직접 로그인한 뒤** headed 브라우저로 캡처해야 한다(2026-07-07에 쓴 PowerShell `PrintWindow` 방식 —
`page.screenshot`은 브라우저 크롬을 안 담아서 주소창이 안 나온다).

로그인 세션을 흉내 내려고 localStorage에 ID 토큰을 넣는 방법은 **쓰지 않는다** — 프론트가 서명검증을 안 하므로
기술적으론 통과하지만, 일어나지 않은 로그인을 증거처럼 남기는 것이라 포폴에 부적합하다.
