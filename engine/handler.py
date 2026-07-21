"""Lambda 진입점 — orchestrator (상관완료 이벤트 → 능동조사 → case/설명 적재). ★프로젝트 심장 배포판.

infra/engine의 orchestrator Lambda가 배포(실코드 스왑 포인트). 로직=Orchestrator(reasoning/orchestrator.py).
2-pass: correlation이 발행한 cnapp.attackpath.correlation.completed로 기동 → RDS finding+attack_path 로드 →
Triage→Hypothesis(실 Bedrock)→Evidence(실 Bedrock tool-use)→Reasoning(실 Bedrock) → cases + finding_explanations 적재.

실/목 스왑(REAL_TOOLS=1 기본): RealToolExecutor + BedrockEvidenceAgent(run_real.py와 동일 구성) +
BedrockHypothesisAgent + BedrockReasoningAgent(2026-07-10 추가, 셋 다 같은 BEDROCK_MODEL_ID 공유 —
현재 계정은 Sonnet Marketplace 구독 미승인이라 전부 Haiku). Evidence는 Phase1에서 실 Bedrock
Haiku가 실 S3를 자가 조사 CONFIRMED로 검증된 그 경로. REAL_TOOLS=0이면 셋 다 MockToolExecutor
+ 템플릿(HypothesisAgent·ReasoningAgent)으로 무비용 복귀.

Lambda 설정:
  handler = "engine.handler.handler"
  env     = DB_HOST · DB_SECRET_ARN · BEDROCK_MODEL_ID(global inference profile) · REAL_TOOLS
  role    = shared evidence-readonly(계약④) + bedrock-invoke 정책(infra/engine에서 attach)
  psycopg2 레이어 + VPC. ⚠️ 실 RDS·실 Bedrock 코드 — apply 세션에서 검증.
  레이어  xray-sdk(2026-07-07 추가, X-Ray 분산 트레이싱 — Bedrock 호출도 subsegment로 보임).
"""
from __future__ import annotations

import json
import os

from engine.reasoning.orchestrator import Orchestrator

# X-Ray(2026-07-07): correlation이 전달한 batch_id를 이 Lambda 세그먼트에도 annotation으로 남겨
# 파이프라인 전체(ingest→normalize→correlation→orchestrator)를 하나의 검색 키로 찾을 수 있게 한다
# (EventBridge 구간은 진짜 트레이스 병합이 아니라 annotation 상관관계 — normalize/handler.py 주석 참고).
try:
    from aws_xray_sdk.core import patch_all, xray_recorder

    patch_all()
    _XRAY = True
except ImportError:
    _XRAY = False


def _xray_annotate(key: str, value: str) -> None:
    """안전한 annotation — 2026-07-08 실측 버그(FacadeSegmentMutationException, pipeline/normalize/
    handler.py 주석 참고) 이후 서브세그먼트 방식 + 광범위 try/except로 통일."""
    if not _XRAY:
        return
    try:
        sub = xray_recorder.begin_subsegment("annotate")
        if sub is not None:
            sub.put_annotation(key, value)
        xray_recorder.end_subsegment()
    except Exception:  # noqa: BLE001
        pass

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
    batch_id = (event or {}).get("detail", {}).get("batch_id")
    if batch_id:
        _xray_annotate("batch_id", batch_id)

    findings = _load(_SELECT_FINDINGS)
    paths = _load(_SELECT_PATHS)  # nodes/edges는 psycopg2가 jsonb→list로 디코드
    if not paths:
        return {"skipped": "no attack paths"}

    # Orchestrator.run()은 paths[0]만 본다(골든 경로 하니스) — 여러 경로를 다 조사하려면
    # 경로마다 [단일 경로]로 나눠 호출하고, 경로별로 독립된 case_id를 줘야 한다(2026-07-21).
    # 안 그러면 correlation이 만든 attack_path 2·3번은 영원히 조사 대상에서 빠진다.
    orch = _orchestrator()
    results = []
    investigated: set = set()  # 경로 case가 실제로 조사한 finding_id — 아래 잔여 처리에서 제외
    for path in paths:
        case_id = _case_id_for_path(path["attack_path_id"])
        try:
            case, _escalated, case_findings = orch.run(findings, [path], case_id=case_id)
        except ValueError:
            continue  # 이 경로엔 조사 가능한(escalate+control 매칭) finding이 없음 — 스킵
        investigated.update(f["finding_id"] for f in case_findings)
        _upsert_case(case)
        _upsert_explanations(case)
        results.append({
            "case": case["case_id"],
            "attack_path_id": path["attack_path_id"],
            # verdict/confidence는 case["evidence_meta"](set_evidence 기록). reasoning엔 narrative·risk_level만.
            "verdict": (case.get("evidence_meta") or {}).get("verdict"),
        })

    # ── 위 경로 case가 조사하지 않은 escalated finding 전부 ──────────────
    # 트리아지 게이트는 "severity_id<=2 OR attack_path_id!=null"인데 경로 case는 두 겹으로
    # 걸러낸다: ① 경로 소속만 보고 ② 그중에서도 _INVESTIGATION_ORDER(hero 경로 전용 control
    # 3종)에 있는 것만 조사한다. 그래서 두 부류가 게이트를 통과하고도 영원히 pending으로 남았다.
    #   ⓐ 경로에 안 붙은 High↑ finding (예: S3-PUBLIC sev1)
    #   ⓑ 경로에는 붙었지만 조사 순서 목록에 없는 finding (예: SECRET-PLAINTEXT)
    # 2026-07-21 라이브 실측: 게이트 통과 19건 중 13건(ⓐ) → ⓐ 처리 후에도 4건(ⓑ)이 남았다.
    # 그래서 "경로 밖"이 아니라 **실제로 조사되지 않은 것 전부**를 기준으로 삼는다.
    # run()은 paths=[]이면 golden_path_id=None → escalated[:3]로 후보를 잡으므로 3건씩 끊어 넘긴다.
    off_path = [
        f for f in findings
        if f["finding_id"] not in investigated and _escalates(f)
    ]
    # 폭주 방지 — 스캐너가 대량 유입되면 Bedrock 비용이 선형으로 늘어난다. 기본 6 case(=18건).
    max_cases = int(os.environ.get("MAX_OFFPATH_CASES", "6"))
    batches = [off_path[i:i + 3] for i in range(0, len(off_path), 3)][:max_cases]
    dropped = len(off_path) - sum(len(b) for b in batches)
    for i, batch in enumerate(batches):
        try:
            case, _e, _cf = orch.run(batch, [], case_id=_case_id_for_offpath(i))
        except ValueError:
            continue
        _upsert_case(case)
        _upsert_explanations(case)
        results.append({
            "case": case["case_id"],
            "attack_path_id": None,
            "verdict": (case.get("evidence_meta") or {}).get("verdict"),
        })

    out = {"cases": results}
    if dropped:
        # 조용히 자르지 않는다 — 잘린 게 있으면 응답에 남겨 다음 호출에서 처리되는지 보이게.
        out["offpath_dropped"] = dropped
    return out


def _escalates(finding: dict) -> bool:
    """트리아지 게이트와 동일 조건(engine/evidence/triage.py) — open + (High↑ or 경로 소속)."""
    from engine.evidence.triage import triage
    return bool(triage(finding).escalate)


def _case_id_for_offpath(index: int) -> str:
    """경로 밖 배치용 결정적 case_id — 경로용(c0000…000N)과 안 겹치게 b 접두 대역을 쓴다.

    재실행해도 같은 배치가 같은 case_id를 받아야 UPSERT가 멱등이다.
    """
    return "b0000000-0000-4000-8000-%012d" % (index + 1)


def _case_id_for_path(attack_path_id: str) -> str:
    """attack_path_id(a0000...000N) -> case_id(c0000...000N) 결정적 매핑.

    correlation.py의 3개 경로 ID(_HERO_PATH_ID 등)가 접두사 'a'만 다른 고정 상수라,
    같은 자리에 'c'를 넣으면 경로별로 유일하고 재현 가능한 case_id가 나온다
    (uuid4 랜덤 생성 대신 — 재실행해도 같은 경로는 같은 case를 upsert해서 중복 케이스 안 쌓임).
    """
    return "c" + attack_path_id[1:]


def _orchestrator() -> Orchestrator:
    """실(Bedrock tool-use) ↔ 목 스왑. run_real.py와 동일 구성.

    2026-07-10: Hypothesis·Reasoning도 REAL_TOOLS 게이트에 합류(같은 BEDROCK_MODEL_ID 공유) —
    Evidence만 실이던 갭을 채움. 셋 다 동일 인터페이스라 주입만으로 스왑, MockToolExecutor
    경로(REAL_TOOLS=0)는 기존 템플릿 3종 그대로.
    """
    if os.environ.get("REAL_TOOLS", "1") != "1":
        return Orchestrator()  # MockToolExecutor(무비용)
    from engine.core.tools import RealToolExecutor
    from engine.evidence.bedrock_planner import BedrockEvidenceAgent
    from engine.reasoning.bedrock_hypothesis import BedrockHypothesisAgent
    from engine.reasoning.bedrock_reasoning import BedrockReasoningAgent
    region = os.environ.get("AWS_REGION", "ap-northeast-2")
    ex = RealToolExecutor(region=region)
    kwargs = {"region": region}
    model_id = os.environ.get("BEDROCK_MODEL_ID")
    if model_id:
        kwargs["model_id"] = model_id
    return Orchestrator(
        executor=ex,
        evidence_agent=BedrockEvidenceAgent(ex, **kwargs),
        hypothesis_agent=BedrockHypothesisAgent(**kwargs),
        reasoning_agent=BedrockReasoningAgent(**kwargs),
        rag_retriever=_rag_retriever(region),
    )


def _rag_retriever(region: str):
    """실 RAG 검색기(Titan 쿼리임베딩 → pgvector cosine). 실패하면 None(=rag_refs 빈 목록).

    2026-07-21까지 orchestrator에 RAG 배선 자체가 없어 `finding_explanations.rag_refs`가
    항상 []였다(감사에서 발견). 여기서 주입해 판정 근거에 지식베이스 control_id가 실리게 한다.
    ⚠️ 지식베이스가 비어 있으면(재apply 직후 등) 검색 결과가 0건이라 rag_refs도 비는데,
       그건 정상 동작이 아니라 적재 누락 신호다 — `python -m rag.corpus.load_live` 참고.
    """
    try:
        import json as _json
        import boto3
        from rag.retrieval.retriever import RAGRetriever
        sm = boto3.client("secretsmanager", region_name=region)
        sec = _json.loads(sm.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"])
        dsn = "host=%s port=5432 dbname=%s user=%s password=%s sslmode=require" % (
            os.environ["DB_HOST"], sec.get("dbname", "cnapp"), sec["username"], sec["password"],
        )
        return RAGRetriever(mock=False, pg_dsn=dsn, region=region)
    except Exception:  # noqa: BLE001 — RAG는 보조 설명이라 실패해도 조사는 계속돼야 한다
        return None


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
                    # 2026-07-21 배선 완료 — orchestrator가 RAG 검색기로 채운 control_id 목록.
                    # (그 전엔 배선이 없어 항상 [] 였다. 비어 있으면 지식베이스 미적재를 의심할 것.)
                    "rag_refs": reasoning.get("rag_refs", []),
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
