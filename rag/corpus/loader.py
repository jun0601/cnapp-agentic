"""RAG 코퍼스 적재기 (준형 담당) — 청크 → 임베딩 → pgvector 적재.

진우 검색부(rag/retrieval)의 **적재 쪽 대칭**. 계약⑥이 이음새:
  - 진우 `mock_corpus.py`가 코퍼스 '내용'(control별 한국어 청크)을 제공.
  - 준형(이 파일)이 그 내용을 **Titan Embed v2로 임베딩(1024-dim)해 pgvector에 적재** →
    계약⑥ 완성(embedding 필드 채움). 검색부는 같은 모델로 쿼리 벡터화해 cosine 검색.
  ※ 적재·검색이 **반드시 같은 임베딩 모델**이어야 벡터가 맞음(계약⑥ embedding_model const).

mock-first (Bedrock·pgvector 없이 흐름 검증):
  embed() = 텍스트 해시 기반 결정적 1024-dim 벡터(실 벡터 아님, 차원·계약만 검증).
  load(dry_run=True) = 적재 시뮬(DB 없이 계약⑥ 청크 생성·검증).
실 경로(지연 import — 게이트):
  embed() = Bedrock `amazon.titan-embed-text-v2:0` invoke_model(1024-dim).
  load(dry_run=False) = psycopg2로 rag_chunks(pgvector) UPSERT. PG_DSN + Bedrock 액세스 필요.
"""
from __future__ import annotations

import hashlib
import random
from typing import List, Optional

# 계약⑥ 고정 상수(embedding_model·dim은 적재·검색 동일 필수 — schema const)
EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
DIM = 1024


class CorpusLoader:
    """청크 → 임베딩 → 적재. mock=결정적 벡터+dry-run / real=Titan+pgvector."""

    def __init__(self, mock: bool = True, pg_dsn: Optional[str] = None,
                 region: str = "ap-northeast-2", profile: Optional[str] = None) -> None:
        self._mock = mock
        self._pg_dsn = pg_dsn
        self._region = region
        self._profile = profile
        self._bedrock = None  # 지연 초기화

    # ── 임베딩 ────────────────────────────────────────────────────────
    def embed(self, text: str) -> List[float]:
        """텍스트 → 1024-dim 벡터. mock=결정적(해시 시드) / real=Titan Embed v2."""
        if self._mock:
            # 텍스트별 결정적 벡터(같은 텍스트=같은 벡터). 실 의미 벡터 아님 — 차원·계약 검증용.
            seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
            rng = random.Random(seed)
            return [rng.uniform(-1.0, 1.0) for _ in range(DIM)]
        return self._titan_embed(text)

    def _titan_embed(self, text: str) -> List[float]:
        """실배포: Bedrock Titan Embed v2로 1024-dim 임베딩(지연 import boto3)."""
        import json
        if self._bedrock is None:
            import boto3
            session = boto3.Session(profile_name=self._profile, region_name=self._region)
            self._bedrock = session.client("bedrock-runtime")
        resp = self._bedrock.invoke_model(
            modelId=EMBEDDING_MODEL,
            body=json.dumps({"inputText": text, "dimensions": DIM, "normalize": True}),
        )
        return json.loads(resp["body"].read())["embedding"]

    # ── 계약⑥ 청크 조립 ──────────────────────────────────────────────
    def to_chunk(self, seed: dict) -> dict:
        """seed(chunk_id·text·metadata) → 계약⑥ 완성 청크(embedding 채움).

        seed는 진우 mock_corpus의 청크(embedding 없음). 여기서 embedding+const 필드 채워
        계약⑥(chunk_id·text·embedding[1024]·embedding_model·dim·metadata) 준수.
        """
        return {
            "chunk_id": seed["chunk_id"],
            "text": seed["text"],
            "embedding": self.embed(seed["text"]),
            "embedding_model": EMBEDDING_MODEL,
            "dim": DIM,
            "metadata": seed["metadata"],
        }

    def load(self, seed_chunks: List[dict], dry_run: bool = True) -> dict:
        """청크[] → 임베딩 → pgvector 적재. dry_run=True면 DB 없이 계약⑥ 청크만 생성(mock).

        반환: {loaded, dim, model, controls, chunks(dry_run일 때만)}.
        실배포: dry_run=False + pg_dsn → rag_chunks 테이블 UPSERT.
        """
        chunks = [self.to_chunk(s) for s in seed_chunks]
        if dry_run or not self._pg_dsn:
            controls = sorted({c["metadata"]["control_id"] for c in chunks})
            return {"loaded": len(chunks), "dim": DIM, "model": EMBEDDING_MODEL,
                    "controls": controls, "chunks": chunks}
        self._pg_upsert(chunks)
        return {"loaded": len(chunks), "dim": DIM, "model": EMBEDDING_MODEL,
                "controls": sorted({c["metadata"]["control_id"] for c in chunks})}

    def _pg_upsert(self, chunks: List[dict]) -> None:
        """실배포: psycopg2로 rag_chunks(pgvector) UPSERT(지연 import)."""
        import json
        import psycopg2  # 지연 import — mock 환경 무영향
        conn = psycopg2.connect(self._pg_dsn)
        try:
            with conn, conn.cursor() as cur:
                for c in chunks:
                    cur.execute(
                        "INSERT INTO rag_chunks (chunk_id, text, embedding, embedding_model, dim, metadata) "
                        "VALUES (%s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (chunk_id) DO UPDATE SET "
                        "text=EXCLUDED.text, embedding=EXCLUDED.embedding, metadata=EXCLUDED.metadata",
                        (c["chunk_id"], c["text"], c["embedding"], c["embedding_model"],
                         c["dim"], json.dumps(c["metadata"])),
                    )
        finally:
            conn.close()


# ── 계약⑥ 검증 헬퍼 ───────────────────────────────────────────────────
def validate_chunk(chunk: dict) -> List[str]:
    """계약⑥ 핵심 정합 검사. 오류 목록 반환(빈 리스트=OK)."""
    errs: List[str] = []
    for k in ("chunk_id", "text", "embedding", "embedding_model", "dim", "metadata"):
        if k not in chunk:
            errs.append("필수키 누락: %s" % k)
    emb = chunk.get("embedding")
    if not isinstance(emb, list) or len(emb) != DIM:
        errs.append("embedding은 %d-dim float 배열이어야 함(현재 %s)"
                    % (DIM, len(emb) if isinstance(emb, list) else type(emb).__name__))
    if chunk.get("embedding_model") != EMBEDDING_MODEL:
        errs.append("embedding_model const 위반: %s" % chunk.get("embedding_model"))
    if chunk.get("dim") != DIM:
        errs.append("dim const 위반: %s" % chunk.get("dim"))
    if "control_id" not in (chunk.get("metadata") or {}):
        errs.append("metadata.control_id 필수")
    return errs
