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
| `POST /remediations/:id/{approve,reject}` | **approver만**(HITL) → SFn StartExecution(스텁) |
| `POST /findings/:id/reanalyze` · `POST /chat` | 재분석(202) · 자연어 질의(에코 스텁) |

## mock ↔ real 스왑 (한 곳)
- `data.ts`: `USE_MOCK=true`(기본) → `contracts/mock-*.json` 읽어 응답 / `USE_MOCK=false`(+`PG_DSN`) → pgvector 쿼리(`pg*` 함수 구현부, 콘솔 §5 스키마).
- `auth.ts`: ALB가 넘긴 `x-amzn-oidc-data`(JWT)의 `custom:groups` → viewer/approver(§7). 로컬/미인증은 viewer.

## 개발·검증
```
cd apps/console-backend
npm install
npm run typecheck   # tsc --noEmit
```
mock 모드 로컬 확인은 핸들러를 직접 호출(ALB 이벤트 형태 dict)하거나, 실배포 시 `dist/handler.handler`를 Lambda 핸들러로 지정.

## 실배포(EKS 세션 아님 — 서버리스)
`infra/console`(ALB `authenticate-cognito` → Lambda 타깃, RDS 동일 VPC, S3+CloudFront 프론트)가 이 코드를 배포. 상세 = console-app-design §4·§12.
