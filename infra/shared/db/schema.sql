-- =============================================================================
-- cnapp-agentic — pgvector 데이터 스키마 (SSOT = contracts/*.schema.json + console-app-design §5)
--
-- 이 파일이 실 데이터 평면의 '빈 공백'을 메운다:
--   pipeline/normalize → findings 적재 · attackpath/correlation → attack_paths · engine → cases
--   rag/corpus → rag_chunks · console-backend(real) → 이 테이블들을 조회
-- 모든 컬럼은 계약①(finding)·③(attack-path)·⑦(case)·⑥(rag-chunk)에서 도출. 어긋나면 contracts가 우선.
--
-- 적용(RDS는 private subnet이라 로컬에서 직접 못 닿음):
--   VPC 내부(마이그레이션 Lambda / 배스천 / normalize·corpus 첫 실행)에서 psql로 이 파일 실행.
--   예) psql "$PG_DSN" -f schema.sql   (DSN은 shared의 Secrets Manager rds_secret_arn에서)
-- 멱등(IF NOT EXISTS)이라 재실행 안전.
-- =============================================================================

-- pgvector 확장(RDS PostgreSQL 16, D9) — rag_chunks.embedding 컬럼 전제
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- findings — OCSF-lite finding (계약① / console §5). 목록·필터·정렬의 주인.
-- =============================================================================
CREATE TABLE IF NOT EXISTS findings (
  finding_id      uuid PRIMARY KEY,
  cloud           text NOT NULL CHECK (cloud IN ('aws', 'azure')),
  resource_id     text NOT NULL,               -- {cloud}:{type}:{native_id} (4.4.1a 캐논)
  resource_type   text NOT NULL,               -- s3_bucket·iam_role·… (계약① enum)
  pillar          text NOT NULL CHECK (pillar IN ('cspm','ciem','vuln','kspm','data','attack_path')),
  control_id      text NOT NULL,               -- INTERNAL-* (control-catalog.json)
  title           text NOT NULL,
  severity_id     int  NOT NULL CHECK (severity_id BETWEEN 1 AND 5),  -- 1=Critical~5=Info(내부 컨벤션)
  status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open','remediated','suppressed')),
  sources         text[] NOT NULL DEFAULT '{}',-- 원본 스캐너 체크 id 누적(dedup 머지)
  dedup_key       text NOT NULL UNIQUE,         -- resource_id|control_id — 중복 제거·상태 매칭
  priority_score  double precision,             -- 엔진 Triage가 채움(초기 NULL)
  attack_path_id  uuid,                         -- 1차 상관(2-pass)이 backfill
  ai_status       text NOT NULL DEFAULT 'pending' CHECK (ai_status IN ('pending','done','failed')),
  first_seen      timestamptz NOT NULL,
  last_seen       timestamptz NOT NULL,
  raw_ref         text                          -- 원본 s3 포인터
);
CREATE INDEX IF NOT EXISTS idx_findings_status  ON findings (status);
CREATE INDEX IF NOT EXISTS idx_findings_cloud   ON findings (cloud);
CREATE INDEX IF NOT EXISTS idx_findings_pillar  ON findings (pillar);
CREATE INDEX IF NOT EXISTS idx_findings_apath   ON findings (attack_path_id);
CREATE INDEX IF NOT EXISTS idx_findings_prio    ON findings (priority_score DESC NULLS LAST);

-- =============================================================================
-- attack_paths — 크로스클라우드 공격경로 그래프 (계약③ / console §5·5.1)
-- nodes/edges는 계약③ JSON 그대로 jsonb 저장 → 콘솔이 React Flow로 렌더(소스 독립).
-- =============================================================================
CREATE TABLE IF NOT EXISTS attack_paths (
  attack_path_id uuid PRIMARY KEY,
  severity_id    int  NOT NULL CHECK (severity_id BETWEEN 1 AND 5),  -- 체인>=3이면 Critical(1)
  nodes          jsonb NOT NULL,   -- [{id,cloud,resource_id,label,pillar}]
  edges          jsonb NOT NULL,   -- [{from,to,type,cross_cloud,label}]
  narrative_text text NOT NULL DEFAULT '',
  created_at     timestamptz NOT NULL DEFAULT now()
);

-- findings.attack_path_id → attack_paths (2-pass: findings 먼저 삽입 후 backfill이라 nullable·SET NULL)
ALTER TABLE findings
  DROP CONSTRAINT IF EXISTS fk_findings_attack_path;
ALTER TABLE findings
  ADD CONSTRAINT fk_findings_attack_path
  FOREIGN KEY (attack_path_id) REFERENCES attack_paths (attack_path_id) ON DELETE SET NULL;

-- =============================================================================
-- cases — 에이전트 능동조사 핸드오프 (계약⑦ / console §5). Evidence 탭·판정의 주인(UC0).
-- 각 에이전트 구간을 jsonb로 저장(triage→hypotheses→evidence→reasoning). 한 finding = 활성 case ≤1.
-- =============================================================================
CREATE TABLE IF NOT EXISTS cases (
  case_id       uuid PRIMARY KEY,
  finding_ids   text[] NOT NULL DEFAULT '{}',  -- 상관 시 여러 finding 묶음
  stage         text NOT NULL CHECK (stage IN ('triage','hypothesis','evidence','reasoning')),
  triage        jsonb,        -- {priority_score, escalate, reason}  ★게이트
  hypotheses    jsonb,        -- string[]
  evidence      jsonb,        -- [{tool,resource_id,result_summary,raw,ts}] (계약②)
  evidence_meta jsonb,        -- {tool_calls_count, confidence_score, verdict}
  reasoning     jsonb,        -- {verdict, confidence_score, narrative, rag_refs}
  model_trace   jsonb,        -- [{stage,model,tokens}] 비용 추적
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
-- finding_id로 case 조회(콘솔 상세 조인) — finding_ids 배열 GIN
CREATE INDEX IF NOT EXISTS idx_cases_finding_ids ON cases USING gin (finding_ids);

-- =============================================================================
-- finding_explanations — AI 설명 카드(UC1, finding당 요약). evidence는 여기 두지 않고 case_id FK만(§5).
-- =============================================================================
CREATE TABLE IF NOT EXISTS finding_explanations (
  finding_id       uuid PRIMARY KEY REFERENCES findings (finding_id) ON DELETE CASCADE,
  ai_summary       text NOT NULL DEFAULT '',
  confidence_score double precision,
  rag_refs         text[] NOT NULL DEFAULT '{}',
  case_id          uuid REFERENCES cases (case_id) ON DELETE SET NULL,  -- nullable(§5)
  ai_status        text NOT NULL DEFAULT 'pending' CHECK (ai_status IN ('pending','done','failed')),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

-- =============================================================================
-- remediation_requests — 조치 승인 플로우(UC4 / console §5·§7 HITL)
-- =============================================================================
CREATE TABLE IF NOT EXISTS remediation_requests (
  id                 uuid PRIMARY KEY,
  finding_id         uuid NOT NULL REFERENCES findings (finding_id) ON DELETE CASCADE,
  proposed_fix_diff  text NOT NULL DEFAULT '',
  status             text NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending','approved','rejected','applied')),
  approver           text,               -- approver(보안관리자) 신원 — 승인 시 채움
  step_function_arn  text,               -- 승인 시 StartExecution한 실행 ARN
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_remediation_finding ON remediation_requests (finding_id);
CREATE INDEX IF NOT EXISTS idx_remediation_status  ON remediation_requests (status);

-- =============================================================================
-- rag_chunks — RAG 코퍼스(계약⑥ / project-draft 16). '컨트롤 1개 = 1청크'. Titan v2 1024-dim.
-- =============================================================================
CREATE TABLE IF NOT EXISTS rag_chunks (
  chunk_id        uuid PRIMARY KEY,
  text            text NOT NULL,
  embedding       vector(1024) NOT NULL,         -- 계약⑥ dim=1024 고정
  embedding_model text NOT NULL DEFAULT 'amazon.titan-embed-text-v2:0',
  dim             int  NOT NULL DEFAULT 1024,
  metadata        jsonb NOT NULL                 -- {cloud,service,framework,control_id,severity,isms_p,lifecycle,remediable}
);
-- control_id로 finding↔청크 조인(검색 폴백·필터)
CREATE INDEX IF NOT EXISTS idx_rag_control ON rag_chunks ((metadata->>'control_id'));
-- cosine similarity ANN 인덱스(pgvector HNSW). 코퍼스 작아 lists/m 기본이면 충분.
CREATE INDEX IF NOT EXISTS idx_rag_embedding ON rag_chunks USING hnsw (embedding vector_cosine_ops);

-- =============================================================================
-- login_events — 실 SSO 로그인 감사(2026-07-08). Cognito Post-Authentication 트리거
-- (apps/console-backend/src/login-trigger.ts)가 로그인 성공마다 1행 기록. 감사로그 페이지가
-- 이 테이블 + remediation_requests + cases + findings를 시간순 병합해서 보여준다
-- (console-backend/src/data.ts getAudit()).
-- =============================================================================
CREATE TABLE IF NOT EXISTS login_events (
  id            uuid PRIMARY KEY,
  actor         text NOT NULL,   -- 이메일(Entra 클레임 email, 없으면 userName)
  role          text NOT NULL,   -- 로그인 시점 판정된 역할(viewer/approver) — 스냅샷, 이후 그룹변경은 반영 안 됨
  logged_in_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_login_events_time ON login_events (logged_in_at DESC);
