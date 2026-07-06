"""Lambda 진입점 — orchestrator (상관완료 이벤트 → 능동조사 → case/설명 적재). ★프로젝트 심장 배포판.

infra/engine의 orchestrator Lambda가 배포(실코드 스왑 포인트). 로직=Orchestrator(reasoning/orchestrator.py).
2-pass: correlation이 발행한 cnapp.attackpath.correlation.completed로 기동 → RDS finding+attack_path 로드 →
Triage→Hypothesis→Evidence(실 Bedrock tool-use)→Reasoning → cases + finding_explanations 적재.

실/목 스왑(REAL_TOOLS=1 기본): RealToolExecutor + BedrockEvidenceAgent(run_real.py와 동일 구성) —
Phase1에서 실 Bedrock Haiku가 실 S3를 자가 조사 CONFIRMED로 검증된 그 경로. 0이면 MockToolExecutor.

Lambda 설정:
  handler = "engine.handler.handler"
  env     = DB_HOST · DB_SECRET_ARN · BEDROCK_MODEL_ID(global inference profile) · REAL_TOOLS
  role    = shared evidence-readonly(계약④) + bedrock-invoke 정책(infra/engine에서 attach)
  psycopg2 레이어 + VPC. ⚠️ 실 RDS·실 Bedrock 코드 — apply 세션에서 검증.
"""
from __future__ import annotations

import json
import os

from engine.reasoning.orchestrator import Orchestrator

_SELECT_FINDINGS = """
SELECT finding_id, cloud, resource_id, resource_type, pillar, control_id,
       title, severity_id, status, sources, dedup_key, priority_score,
       attack_path_id, ai_status
FROM findings
WHERE status = 'open';
"""

_SELECT_PATHS = "SELECT attack_path_id, severity_id, nodes, edges, narrative_text FROM attack_paths;"

_UPSERT_CASE = """
INSERT INTO cases (case_id, finding_ids, stage, triage, hypotheses, evidence,
                   evidence_meta, reasoning, model_trace, updated_at)
VALUES (%(case_id)s, %(finding_ids)s, %(stage)s, %(triage)s, %(hypotheses)s, %(evidence)s,
        %(evidence_meta)s, %(reasoning)s, %(model_trace)s, now())
ON CONFLICT (case_id) DO UPDATE SET
  finding_ids   = EXCLUDED.finding_ids,
  stage         = EXCLUDED.stage,
  triage        = EXCLUDED.triage,
  hypotheses    = EXCLUDED.hypotheses,
  evidence      = EXCLUDED.evidence,
  evidence_meta = EXCLUDED.evidence_meta,
  reasoning     = EXCLUDED.reasoning,
  model_trace   = EXCLUDED.model_trace,
  updated_at    = now();
"""

_UPSERT_EXPL = """
INSERT INTO finding_explanations (finding_id, ai_summary, confidence_score, rag_refs, case_id, ai_status, updated_at)
VALUES (%(finding_id)s, %(ai_summary)s, %(confidence_score)s, %(rag_refs)s, %(case_id)s, 'done', now())
ON CONFLICT (finding_id) DO UPDATE SET
  ai_summary       = EXCLUDED.ai_summary,
  confidence_score = EXCLUDED.confidence_score,
  rag_refs         = EXCLUDED.rag_refs,
  case_id          = EXCLUDED.case_id,
  ai_status        = 'done',
  updated_at       = now();
"""


def handler(event: dict, context=None) -> dict:
    findings = _load(_SELECT_FINDINGS)
    paths = _load(_SELECT_PATHS)  # nodes/edges는 psycopg2가 jsonb→list로 디코드
    if not paths:
        return {"skipped": "no attack paths"}

    case, _escalated, _case_findings = _orchestrator().run(findings, paths)
    _upsert_case(case)
    _upsert_explanations(case)
    return {
        "case": case["case_id"],
        # verdict/confidence는 case["evidence_meta"](set_evidence 기록). reasoning엔 narrative·risk_level만.
        "verdict": (case.get("evidence_meta") or {}).get("verdict"),
    }


def _orchestrator() -> Orchestrator:
    """실(Bedrock tool-use) ↔ 목 스왑. run_real.py와 동일 구성."""
    if os.environ.get("REAL_TOOLS", "1") != "1":
        return Orchestrator()  # MockToolExecutor(무비용)
    from engine.core.tools import RealToolExecutor
    from engine.evidence.bedrock_planner import BedrockEvidenceAgent
    region = os.environ.get("AWS_REGION", "ap-northeast-2")
    ex = RealToolExecutor(region=region)
    kwargs = {"region": region}
    model_id = os.environ.get("BEDROCK_MODEL_ID")
    if model_id:
        kwargs["model_id"] = model_id
    return Orchestrator(executor=ex, evidence_agent=BedrockEvidenceAgent(ex, **kwargs))


def _case_finding_ids(case: dict) -> list:
    fin = case.get("finding", {})
    if "finding_ids" in fin:
        return fin["finding_ids"]
    return [fin["finding_id"]] if fin.get("finding_id") else []


def _upsert_case(case: dict) -> None:
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(_UPSERT_CASE, {
                "case_id": case["case_id"],
                "finding_ids": _case_finding_ids(case),
                "stage": case.get("stage", "reasoning"),
                "triage": _j(case.get("triage")),
                "hypotheses": _j(case.get("hypotheses")),
                "evidence": _j(case.get("evidence")),
                "evidence_meta": _j(case.get("evidence_meta")),
                "reasoning": _j(case.get("reasoning")),
                "model_trace": _j(case.get("model_trace")),
            })
    finally:
        conn.close()


def _upsert_explanations(case: dict) -> None:
    """case에 속한 finding들에 AI 설명 카드(UC1) + ai_status=done 반영."""
    reasoning = case.get("reasoning") or {}
    meta = case.get("evidence_meta") or {}  # confidence_score·verdict는 여기(set_evidence 기록)
    fids = _case_finding_ids(case)
    if not fids:
        return
    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            for fid in fids:
                cur.execute(_UPSERT_EXPL, {
                    "finding_id": fid,
                    "ai_summary": reasoning.get("narrative", ""),
                    "confidence_score": meta.get("confidence_score"),
                    "rag_refs": reasoning.get("rag_refs", []),  # RAG 연동 전엔 []( reasoning엔 아직 미기록)
                    "case_id": case["case_id"],
                })
                cur.execute("UPDATE findings SET ai_status = 'done' WHERE finding_id = %s;", (fid,))
    finally:
        conn.close()


def _load(sql: str) -> list:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def _j(value):
    return json.dumps(value) if value is not None else None


def _connect():
    import boto3
    import psycopg2
    sm = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "ap-northeast-2"))
    sec = json.loads(sm.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"])
    return psycopg2.connect(
        host=os.environ["DB_HOST"], port=5432,
        dbname=sec.get("dbname", "cnapp"), user=sec["username"], password=sec["password"],
        connect_timeout=5,
        sslmode="require",  # in-transit TLS 강제(#2). 기본 'prefer'는 TLS 선택적 → require로 필수화(CA 핀닝 verify-full은 후속).
    )
