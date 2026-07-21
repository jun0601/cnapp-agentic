"""RAG 코퍼스 **실적재** 진입점 — 재apply 때마다 반복 실행하는 운영 스크립트.

왜 이 파일이 필요한가(2026-07-21 감사에서 발견):
  `loader.py`에 실적재 경로(`CorpusLoader(mock=False)` → Titan → pgvector UPSERT)는
  구현돼 있었지만 **레포 전체에서 그걸 호출하는 곳이 0건**이었다(CI도 run_demo=mock만).
  그래서 인프라를 destroy→재apply 하면 `rag_chunks`가 빈 채로 남고,
  콘솔 `/chat`은 청크 0개로 검색해 **근거 없이 Bedrock 자체 지식으로 답한다**
  (화면의 "RAG · 실 지식베이스" 표시가 사실이 아니게 됨). 실제로 그 상태였다.
  → 이 스크립트가 "적재 절차"를 코드로 고정해 그 사고를 막는다.

RDS는 private subnet이라 **로컬에서 직접 붙지 못한다.** 그래서 두 경로를 지원한다:

  ① --emit-sql <파일>  (로컬에서 쓰는 기본 경로)
      Bedrock Titan은 퍼블릭 API라 로컬에서 임베딩이 된다. 임베딩까지만 로컬에서 하고
      INSERT 문을 파일로 떨군 뒤, EKS 안 psql 파드로 적용한다(스키마·시드와 동일한 방식).

  ② --direct           (VPC 안에서 실행할 때)
      PG_DSN으로 psycopg2 직결. Lambda/파드 등 VPC 내부에서만 동작.

사용:
  # ① 로컬에서 SQL 생성 → EKS psql 파드로 적용(권장)
  python -m rag.corpus.load_live --emit-sql rag_chunks.sql
  #   (생성된 SQL 적용법은 --emit-sql 실행 후 출력되는 안내 참고)

  # ② VPC 안에서 직접 적재
  PG_DSN='postgresql://user:pw@host:5432/db' python -m rag.corpus.load_live --direct

검증:
  적재 후 콘솔 `/api/system`의 `rag.chunks`가 0이 아니어야 하고,
  `/chat` 응답의 `refs`가 비어 있지 않아야 한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from rag.corpus.loader import CorpusLoader, DIM, EMBEDDING_MODEL, validate_chunk
from rag.retrieval import mock_corpus

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _sql_literal(s: str) -> str:
    """SQL 문자열 리터럴 이스케이프(작은따옴표 중복)."""
    return "'" + s.replace("'", "''") + "'"


def _vector_literal(vec: list) -> str:
    """pgvector 입력 형식 — '[0.1,0.2,...]'::vector."""
    return "'[" + ",".join(repr(round(float(v), 6)) for v in vec) + "]'::vector"


def emit_sql(chunks: list, path: str) -> None:
    """INSERT 문을 파일로. psql 파드로 적용하는 경로(RDS가 private이라 로컬 직결 불가)."""
    lines = [
        "-- rag_chunks 실적재 (rag/corpus/load_live.py --emit-sql 생성물)",
        "-- 임베딩: %s (%d-dim, Bedrock에서 실제 생성)" % (EMBEDDING_MODEL, DIM),
        "-- 재실행 안전: chunk_id PK 기준 UPSERT",
        "BEGIN;",
    ]
    for c in chunks:
        lines.append(
            "INSERT INTO rag_chunks (chunk_id, text, embedding, embedding_model, dim, metadata) VALUES ("
            + ", ".join(
                [
                    _sql_literal(c["chunk_id"]) + "::uuid",
                    _sql_literal(c["text"]),
                    _vector_literal(c["embedding"]),
                    _sql_literal(c["embedding_model"]),
                    str(c["dim"]),
                    _sql_literal(json.dumps(c["metadata"], ensure_ascii=True)) + "::jsonb",
                ]
            )
            + ") ON CONFLICT (chunk_id) DO UPDATE SET "
            "text=EXCLUDED.text, embedding=EXCLUDED.embedding, metadata=EXCLUDED.metadata;"
        )
    lines.append("COMMIT;")
    lines.append("SELECT count(*) AS rag_chunks FROM rag_chunks;")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="RAG 코퍼스 실적재(Titan 임베딩 → pgvector)")
    ap.add_argument("--emit-sql", metavar="PATH", help="임베딩 후 INSERT SQL을 파일로 생성(로컬 경로)")
    ap.add_argument("--direct", action="store_true", help="PG_DSN으로 직접 적재(VPC 내부에서만)")
    ap.add_argument("--region", default=os.environ.get("AWS_REGION", "ap-northeast-2"))
    args = ap.parse_args()

    if not args.emit_sql and not args.direct:
        ap.error("--emit-sql 또는 --direct 중 하나를 지정해야 한다")

    seeds = mock_corpus.all_chunks()
    controls = mock_corpus.covered_controls()
    print("코퍼스: 청크 %d개 · control %d종" % (len(seeds), len(controls)))
    print("임베딩 모델: %s (%d-dim) — 실 Bedrock 호출" % (EMBEDDING_MODEL, DIM))

    loader = CorpusLoader(mock=False, region=args.region,
                          pg_dsn=os.environ.get("PG_DSN") if args.direct else None)

    chunks = []
    for i, s in enumerate(seeds, 1):
        c = loader.to_chunk(s)  # 여기서 Titan 실호출
        errs = validate_chunk(c)
        if errs:
            print("  ✗ 계약⑥ 위반 %s: %s" % (c.get("chunk_id"), errs))
            return 1
        chunks.append(c)
        if i % 5 == 0 or i == len(seeds):
            print("  임베딩 %d/%d" % (i, len(seeds)))

    if args.direct:
        if not os.environ.get("PG_DSN"):
            print("✗ PG_DSN 미설정 — --direct는 VPC 내부에서 PG_DSN과 함께 실행해야 한다")
            return 1
        loader.load(seeds, dry_run=False)
        print("✓ pgvector 적재 완료: %d청크 / control %d종" % (len(chunks), len(controls)))
        return 0

    emit_sql(chunks, args.emit_sql)
    print("✓ SQL 생성: %s (%d청크)" % (args.emit_sql, len(chunks)))
    print()
    print("적용 방법 — RDS가 private이라 EKS 안에서 psql로 넣는다:")
    print("  kubectl run pg-load --image=postgres:16 --restart=Never -n default \\")
    print("    --env=PGPASSWORD=\"$DB_PASS\" -- sleep 3600")
    print("  kubectl cp %s pg-load:/tmp/rag.sql" % args.emit_sql)
    print("  kubectl exec pg-load -- psql -h <RDS_HOST> -U <USER> -d <DB> -f /tmp/rag.sql")
    print("  kubectl delete pod pg-load")
    print()
    print("검증: curl -s https://cnapp-agentic.cloud/api/system | grep chunks   # 0이 아니어야 함")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
