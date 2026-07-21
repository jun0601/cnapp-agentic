# apps/console-backend — 관제 콘솔 백엔드 (ALB → Lambda)

> 프론트(`apps/console`)가 기대하는 findings 읽기 API를 제공하는 **서버**.
> `apps/console/src/mocks/handlers.ts`(MSW)의 **서버판** — 같은 계약(§15.2)을 그대로 응답한다.
> **폴리글랏:** console(프론트+백엔드) = TypeScript / engine·pipeline = Python. 이음새는 contracts.

## 왜 있나 (콘솔 실데이터 스왑의 keystone)
지금 콘솔은 MSW가 `contracts/mock-*.json`을 서빙해 백엔드 0으로 돈다. 이 백엔드가 그 자리를 대체:
프론트 `VITE_USE_MOCK=false` + `VITE_API_BASE=<ALB URL>` → 이 Lambda가 응답(**프론트 코드 무변**, §15.5 스왑 포인트).

## API 표면 (§15.2 — 전부 read-only, 쓰기는 SFn로만)
| 메서드·경로 | 응답 |
|---|---|
| `GET /findings?cloud&pillar&status&sort` | `Finding[]` (필터·정렬) |
| `GET /findings/:id` | `{ finding, explanation, case }` (UC0·UC1 조인) |
| `GET /attack-paths` · `GET /attack-paths/:id` | `AttackPath[]` · `AttackPath` |
| `GET /scores` · `GET /audit` · `GET /compliance` | 대시보드 점수 · 감사 · ISMS-P |
| `POST /remediations/:id/{approve,reject}` | **approver만**(HITL) → `remediation_requests` INSERT → **Step Functions StartExecution**(실 배선, 2026-07-08) |
| `POST /findings/:id/reanalyze` | approver만 → orchestrator Lambda **비동기 invoke**(실 Bedrock 재조사) → 202 |
| `POST /chat` | **실 RAG** — Titan Embed v2 → pgvector cosine top-4 → Bedrock converse. 응답에 근거 청크(`refs[].control`) 포함 |
| `GET /system` | AI·시스템 관측 — 모델·RAG 지식베이스 통계·Bedrock 24h 사용량(CloudWatch) |

## mock ↔ real 스왑 (한 곳)
- `data.ts`: `USE_MOCK=true` → `contracts/mock-*.json` 읽어 응답 / `USE_MOCK=false` → pgvector 쿼리(`pg*` 함수 구현부, 콘솔 §5 스키마).
  - ⚠️ **기본값이 환경에 따라 다르다**(2026-07-21): 로컬·CI는 `mock`(contracts가 있으니 안전), **Lambda는 `real`**. Lambda 번들엔 `contracts/`가 없어서 mock으로 폴백하면 `readFileSync`가 그대로 터지기 때문 — fail-safe 방향을 환경에 맞춘 것. terraform이 `USE_MOCK`을 명시 주입하지만 그게 유실돼도 살아남는다.
- `auth.ts`: **Bearer ID 토큰**(SPA 직접 OIDC, 옵션 B) 또는 ALB `x-amzn-oidc-data`의 `custom:groups`(GUID) → viewer/approver(§7). `aws-jwt-verify`로 **JWKS 서명·issuer·audience·exp 검증**하고, 검증기 미구성·검증 실패 시 **fail-closed(viewer)**.

## 개발·검증
```
cd apps/console-backend
npm install
npm run typecheck   # tsc --noEmit
```
mock 모드 로컬 확인은 핸들러를 직접 호출(ALB 이벤트 형태 dict)하거나, 실배포 시 `dist/handler.handler`를 Lambda 핸들러로 지정.

## 실배포(EKS 세션 아님 — 서버리스)
`infra/console`(ALB `authenticate-cognito` → Lambda 타깃, RDS 동일 VPC, S3+CloudFront 프론트)가 이 코드를 배포. 상세 = console-app-design §4·§12.
