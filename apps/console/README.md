# apps/console — CNAPP 관제 앱

CNAPP 보안 관제 대시보드(NOVA 대응). findings·attack-path·AI 설명·조치 승인을 보여주는 플랫폼의 "얼굴".
설계 SSOT = [docs/console-app-design.md](../../docs/console-app-design.md) §15.

## 스택 (§15.1 확정)

Vite + React + TypeScript · React Router · TanStack Query · Tailwind · **React Flow**(attack-path) · Recharts · **MSW**(목업) · 타입은 `contracts/*.schema.json`에서 생성.

## 목업 우선 — 백엔드·AWS 0으로 전 화면 동작

`VITE_USE_MOCK=true`(기본)면 **MSW**가 API를 가로채 [`contracts/mock-*.json`](../../contracts/)을 서빙한다. 엔진·스캐너·인프라 없이 데모 동선(§15.6)이 다 돈다.

```bash
npm install
npm run msw:init      # public/mockServiceWorker.js 생성(최초 1회)
npm run dev           # http://localhost:5173
```

## 실데이터 전환 (§15.5 스왑 포인트)

`.env`에 `VITE_USE_MOCK=false` + `VITE_API_BASE=<ALB URL>`. **화면 코드 무변경**(계약 동일) — MSW만 꺼진다.

## 스크립트

| 명령 | 설명 |
|---|---|
| `npm run dev` | 로컬 개발 서버(MSW on) |
| `npm run build` | 타입체크 + 정적 빌드 → `dist/`(→ infra/console가 S3+CloudFront 배포) |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run gen:types` | `contracts/*.schema.json` → `src/api/contract-types.d.ts` 재생성(계약=타입 SSOT) |
| `npm run msw:init` | MSW 서비스워커 생성 |

## 폴더 (§15.3)

```
src/
├── api/         client.ts(typed fetch) · queries.ts(TanStack) · types.ts(계약 타입)
├── components/  SeverityBadge · FindingCard · PillarFilter · ScoreCard · EvidenceTab · AttackPathGraph · EmptyState
├── mocks/       handlers.ts(MSW ← contracts/mock-*.json) · browser.ts
├── pages/       Dashboard · Findings · FindingDetail · AttackPath · Remediation · Compliance · Audit · Login
├── lib/         auth.ts(Cognito/RBAC) · severity.ts
├── App.tsx · router.tsx · main.tsx
```

## 화면 ↔ mock (§15.4)

| 화면 | 먹는 mock |
|---|---|
| Findings 목록·상세 | `mock-findings.json` (20건) |
| Finding 상세 — Evidence 탭 | `mock-cases.json` (finding_id∈case.finding_ids 조인, UC0 능동조사) |
| Finding 상세 — AI 설명 | finding당 파생 explanation (`ai_status`≠done이면 placeholder) |
| Attack-path 그래프 | `mock-attack-paths.json` (골든 1경로, cross_cloud 강조) |
| 대시보드 점수 | 목업 상수 |

> **데모 심장(§15.6):** 대시보드 → Findings(우선순위) → Finding 상세 **Evidence 탭(AI가 read-only API 4회 호출)** → Attack-path(AWS→Azure 횡단) → 조치 승인.
