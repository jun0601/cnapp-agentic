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

from typing import Optional

from rag.retrieval.mock_corpus import get_chunks_by_control


class RAGRetriever:
    """RAG 청크 검색기.

    mock=True (기본): control_id 정확 매핑
    mock=False:       query_text → Titan Embed v2 벡터화 → pgvector cosine 검색
    """

    def __init__(self, mock: bool = True) -> None:
        self._mock = mock
        if not mock:
            # 실배포: pgvector 연결 준비
            # import os, psycopg2
            # self._conn = psycopg2.connect(os.environ["PG_DSN"])
            raise NotImplementedError("실배포 모드는 PG_DSN + psycopg2 설정 후 활성화")

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
            계약⑥ 청크 딕셔너리 목록 (embedding 필드 제외 — 목업에서는 불필요)
        """
        if self._mock:
            chunks = get_chunks_by_control(control_id)
            return chunks[:top_k]

        # 실배포 경로: query_text → Titan Embed v2 → pgvector
        raise NotImplementedError("실배포: Titan Embed v2 + pgvector 검색 구현 필요")

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
