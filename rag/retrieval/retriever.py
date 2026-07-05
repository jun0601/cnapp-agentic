"""RAG 검색기 (진우 담당).

목업 모드: control_id 직접 매핑 (pgvector 없이 end-to-end 흐름 검증)
실배포:   Titan Embed v2(1024-dim)로 query_text 벡터화 → pgvector cosine similarity 검색

계약⑥ 연결:
  chunk.metadata.control_id == finding.control_id (동일 택소노미)
  → finding을 주면 관련 청크를 바로 검색 가능

실배포 전환 체크리스트:
  1. PG_DSN 환경변수 설정 (RDS pgvector DSN)
  2. 준형이형 corpus 적재 완료 확인 (rag/corpus/)
  3. mock=False 로 교체
"""
from __future__ import annotations

import os
from typing import Optional

from rag.retrieval.mock_corpus import get_chunks_by_control


class RAGRetriever:
    """RAG 청크 검색기.

    mock=True (기본): control_id 정확 매핑
    mock=False:       query_text → Titan Embed v2 벡터화 → pgvector cosine 검색
                      (2026-07-04 실 경로 구현 — 적재부 CorpusLoader와 동일 Titan 모델로 쿼리 임베딩)
    """

    def __init__(self, mock: bool = True, pg_dsn: Optional[str] = None,
                 region: str = "ap-northeast-2", profile: Optional[str] = None) -> None:
        self._mock = mock
        self._pg_dsn = pg_dsn or os.environ.get("PG_DSN")
        self._region = region
        self._profile = profile
        self._conn = None      # psycopg2 연결(지연)
        self._embedder = None  # 쿼리 임베딩용(적재와 반드시 동일 모델)
        if not mock and not self._pg_dsn:
            raise ValueError("실배포 모드는 pg_dsn 또는 PG_DSN 환경변수 필요")

    # ── 실 경로 헬퍼(지연 import — mock/CI 무영향) ──────────────────────
    def _connect(self):
        if self._conn is None:
            import psycopg2
            self._conn = psycopg2.connect(self._pg_dsn, connect_timeout=5)
        return self._conn

    def _embed_query(self, text: str) -> list[float]:
        """쿼리 텍스트 → 1024-dim. ★적재(CorpusLoader)와 반드시 같은 Titan v2 모델(벡터 정합)."""
        if self._embedder is None:
            from rag.corpus.loader import CorpusLoader
            self._embedder = CorpusLoader(mock=False, region=self._region, profile=self._profile)
        return self._embedder.embed(text)

    @staticmethod
    def _vec_literal(vec: list[float]) -> str:
        # pgvector 리터럴 '[v1,v2,...]' — psycopg2가 vector 타입을 몰라 문자열+캐스트로 전달
        return "[" + ",".join("%.6f" % v for v in vec) + "]"

    def search(
        self,
        control_id: str,
        query_text: Optional[str] = None,
        top_k: int = 3,
    ) -> list[dict]:
        """control_id 기반 관련 청크 검색.

        Args:
            control_id: finding.control_id (계약⑥ metadata.control_id와 동일 택소노미)
            query_text: 실배포 시 벡터 검색 쿼리 (목업에서는 미사용)
            top_k:      반환할 최대 청크 수

        Returns:
            계약⑥ 청크 딕셔너리 목록 (chunk_id·text·metadata + 실 경로는 score)
        """
        if self._mock:
            chunks = get_chunks_by_control(control_id)
            return chunks[:top_k]

        # 실 경로: query_text(없으면 control_id) → Titan v2 임베딩 → pgvector cosine top_k.
        # <=> = 코사인 거리(작을수록 유사). score = 1 - 거리(클수록 유사). 같은 control_id 청크가
        # finding 제목과 의미적으로 가장 가까워 자연히 상위에 랭크됨(계약⑥ 택소노미 정합).
        qvec = self._vec_literal(self._embed_query(query_text or control_id))
        sql = (
            "SELECT chunk_id, text, metadata, 1 - (embedding <=> %s::vector) AS score "
            "FROM rag_chunks ORDER BY embedding <=> %s::vector LIMIT %s"
        )
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(sql, (qvec, qvec, top_k))
            rows = cur.fetchall()
        return [
            {"chunk_id": str(r[0]), "text": r[1], "metadata": r[2], "score": float(r[3])}
            for r in rows
        ]

    def search_by_finding(self, finding: dict, top_k: int = 3) -> list[dict]:
        """finding 객체에서 control_id 추출해 검색 (편의 메서드)."""
        control_id = finding.get("control_id", "")
        title = finding.get("title", "")
        return self.search(control_id, query_text=title, top_k=top_k)

    def search_multi(self, findings: list[dict], top_k_each: int = 2) -> dict[str, list[dict]]:
        """여러 finding에 대해 일괄 검색.

        Returns:
            {finding_id: [chunk, ...]} 딕셔너리
        """
        result: dict[str, list[dict]] = {}
        seen_controls: dict[str, list[dict]] = {}  # control_id 중복 검색 방지

        for f in findings:
            fid = f.get("finding_id", "")
            ctrl = f.get("control_id", "")

            if ctrl not in seen_controls:
                seen_controls[ctrl] = self.search(ctrl, top_k=top_k_each)

            result[fid] = seen_controls[ctrl]

        return result
