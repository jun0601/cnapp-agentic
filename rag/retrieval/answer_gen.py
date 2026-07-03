"""RAG 답변 생성기 (진우 담당).

목업: 검색된 청크 + finding + evidence → 템플릿 기반 한국어 설명
실배포: Bedrock Claude Sonnet converse API — 청크 내용을 system prompt에 주입

용도:
  UC1 (finding별 설명): retriever.search_by_finding() → answer_gen.generate()
  UC0 (case 내러티브 보강): Orchestrator Reasoning 단계에서 case.reasoning.rag_refs 채움

실배포 전환 체크리스트:
  1. AWS_REGION=ap-northeast-2 + Bedrock 모델 액세스 활성화
  2. mock=False 로 교체
  3. Bedrock model_id 서울 inference profile ID로 확정 (현재 플레이스홀더)
"""
from __future__ import annotations

from typing import Optional

_SEV_LABEL = {1: "Critical", 2: "High", 3: "Medium", 4: "Low", 5: "Info"}

# Global inference profile ID(2026-07-03 aws bedrock list-inference-profiles 서울 확인 후 확정).
#   기존 bare name "anthropic.claude-sonnet-4-5"는 Bedrock에서 404였음 → 확정 ID로 교체.
#   Haiku(엔진)가 global.anthropic.claude-haiku-4-5-20251001-v1:0인 것과 동일 방식(Global 프로파일).
#   Sonnet(설명 생성)은 Haiku보다 상위 티어 — RAG 내러티브 품질에 사용(비용 티어링, cost-strategy).
_BEDROCK_MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"


def _mock_explanation(finding: dict, chunks: list[dict], evidence: list[dict]) -> str:
    """목업: 청크 요약 + finding 정보 조합 → 설명 텍스트."""
    sev = _SEV_LABEL.get(finding.get("severity_id", 5), "Unknown")
    title = finding.get("title", finding.get("control_id", ""))
    resource = finding.get("resource_id", "")

    risk_text = chunks[0]["text"] if chunks else "관련 지식베이스 항목이 없습니다."
    remedy_text = chunks[1]["text"] if len(chunks) > 1 else ""

    ev_summary = ""
    if evidence:
        ev_summary = (
            "\n\n에이전트 조사(%d회)에서 실환경 위험이 추가로 확인되었습니다." % len(evidence)
        )

    lines = [
        "【%s 등급】 %s" % (sev, title),
        "리소스: %s" % resource,
        "",
        risk_text,
    ]
    if remedy_text:
        lines += ["", "권고 조치:", remedy_text]
    if ev_summary:
        lines.append(ev_summary)

    return "\n".join(lines)


class RAGAnswerGenerator:
    """finding + 검색된 청크 → 한국어 설명 생성.

    mock=True (기본): 템플릿 기반 설명
    mock=False:       Bedrock Claude Sonnet converse API 호출
    """

    def __init__(self, mock: bool = True) -> None:
        self._mock = mock

    def generate(
        self,
        finding: dict,
        chunks: list[dict],
        evidence: Optional[list[dict]] = None,
    ) -> dict:
        """finding + 청크 → 설명 딕셔너리 반환.

        Args:
            finding:  계약① OCSF-lite finding 딕셔너리
            chunks:   retriever.search_by_finding() 결과 청크 목록 (계약⑥)
            evidence: 선택 — case.evidence 목록 (에이전트 조사 결과, 있으면 설명에 반영)

        Returns:
            explanation:  한국어 설명 문자열
            rag_refs:     사용된 chunk_id 목록 (case.reasoning.rag_refs에 채움)
            model_trace:  모델 사용 정보 (case.model_trace 항목으로 추가 가능)
        """
        evidence = evidence or []
        rag_refs = [c["chunk_id"] for c in chunks]

        if self._mock:
            explanation = _mock_explanation(finding, chunks, evidence)
            model_trace = {"stage": "rag_answer", "model": "mock", "tokens": 0}
        else:
            explanation = self._bedrock_generate(finding, chunks, evidence)
            model_trace = {
                "stage": "rag_answer",
                "model": _BEDROCK_MODEL_ID,
                "tokens": -1,  # 실 호출 후 response["usage"]["totalTokens"]로 채움
            }

        return {
            "explanation": explanation,
            "rag_refs": rag_refs,
            "model_trace": model_trace,
        }

    def _bedrock_generate(
        self, finding: dict, chunks: list[dict], evidence: list[dict]
    ) -> str:
        """실배포: Bedrock Claude Sonnet converse 호출 (boto3 지연 import)."""
        import boto3  # 지연 import — 목업 환경 영향 없음

        chunk_texts = "\n\n".join(
            "【지식베이스 %d】\n%s" % (i + 1, c["text"]) for i, c in enumerate(chunks)
        )
        ev_texts = (
            "\n".join(
                "- [%s] %s" % (e.get("tool", ""), e.get("result_summary", ""))
                for e in evidence
            )
            if evidence
            else "(에이전트 조사 없음)"
        )

        system_prompt = (
            "당신은 클라우드 보안 전문가입니다. "
            "아래 지식베이스를 참고해 보안 발견 항목을 한국어로 명확하게 설명하세요.\n\n"
            "지식베이스:\n%s" % chunk_texts
        )
        user_prompt = (
            "보안 발견 항목:\n"
            "- 제목: %s\n"
            "- 리소스: %s\n"
            "- 등급: %s\n\n"
            "에이전트 조사 결과:\n%s\n\n"
            "이 발견 항목의 위험성과 권고 조치를 2~3문단으로 설명해주세요."
            % (
                finding.get("title", ""),
                finding.get("resource_id", ""),
                _SEV_LABEL.get(finding.get("severity_id", 5), "Unknown"),
                ev_texts,
            )
        )

        client = boto3.client("bedrock-runtime", region_name="ap-northeast-2")
        response = client.converse(
            modelId=_BEDROCK_MODEL_ID,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
        )
        return response["output"]["message"]["content"][0]["text"]
