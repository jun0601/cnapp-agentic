"""Reasoning 에이전트 실배포판 — Bedrock LLM 호출로 내러티브 생성.

`reasoning.py` 상단 docstring이 명시한 스왑 범위 그대로: **"analyze() 내 내러티브 생성
부분을 Bedrock Sonnet LLM 호출로 교체"** — narrative만 LLM으로 바꾸고, risk_level·
recommended_actions는 `reasoning.py`의 기존 결정론적 로직(`_risk_level`·`_recommended_actions`)을
그대로 재사용한다. 위험도·조치 카탈로그 매핑은 단순 규칙이라 LLM에 맡길 이유가 없고(일관성·
재현성이 더 중요), 자연어 설명만 LLM이 담당하는 게 문서화된 원래 스왑 범위에 충실하다.

인터페이스는 `ReasoningAgent`와 동일: `analyze(case, findings_map) -> dict`.
→ Orchestrator에 `reasoning_agent=BedrockReasoningAgent()`로 주입하면 스왑.

boto3는 지연 import — 미설치/무자격 환경에서도 이 모듈 import·py_compile은 안전.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from engine.reasoning.reasoning import _recommended_actions, _risk_level

# Reasoning은 최종 내러티브(사람이 읽는 설명·근거)라 원래 의도는 Sonnet 티어(project-draft §15)지만,
# 이 계정은 Sonnet의 Bedrock Marketplace 구독이 미승인 상태(AccessDeniedException, 2026-07-06
# RAG 스왑 때와 동일 계정 제약 — 콘솔 수동 승인 필요, API로 우회 불가). rag/answer_gen.py가 이미
# 겪은 것과 같은 이유로 접근 열린 Haiku로 임시 대체(승인 나면 model_id 생성자 인자로 Sonnet 전달).
DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"


def _short_model_label(model_id: str) -> str:
    """model_trace에 남길 짧은 티어 라벨(bedrock_hypothesis.py와 동일 헬퍼, 독립 배포 유지 위해 중복)."""
    m = model_id.lower()
    if "haiku" in m:
        return "haiku"
    if "sonnet" in m:
        return "sonnet"
    return model_id


_SYSTEM_PROMPT = (
    "너는 클라우드 보안 사고 리포트 작성 에이전트다. Evidence 에이전트가 read-only API로 "
    "수집한 증거를 바탕으로, 보안 분석가가 읽을 한국어 내러티브를 2~4문장으로 작성한다. "
    "규칙:\n"
    "1) 몇 회 조사했는지, 무엇을 확인했는지, 판정(confirmed/inconclusive/refuted)과 신뢰도를 "
    "자연스러운 문장으로 녹여낸다.\n"
    "2) 증거에 없는 내용을 추측해서 쓰지 않는다 — 오직 제공된 evidence·verdict에만 근거한다.\n"
    "3) confirmed면 긴급성을, refuted면 오탐 가능성을 명확히 전달한다.\n"
    "4) 설명체가 아니라 리포트체로 — 불필요한 서론 없이 바로 본론.\n"
    "5) 순수 텍스트만 출력한다 — 마크다운 제목(#)·굵게(**)·목록 기호 등 서식 문자는 "
    "절대 쓰지 않는다(콘솔이 평문으로 그대로 렌더링한다)."
)


def _user_prompt(case: dict, findings_map: Dict[str, dict]) -> str:
    meta = case.get("evidence_meta", {})
    finding_ids = case.get("finding", {}).get("finding_ids", [])
    titles = [
        (findings_map.get(fid, {}).get("title") or findings_map.get(fid, {}).get("control_id", fid))
        for fid in finding_ids
    ]
    evidence_lines = [
        "- [%s] %s" % (e.get("tool", "?"), e.get("result_summary", ""))
        for e in case.get("evidence", [])
    ]
    return (
        "케이스 대상 finding: %s\n"
        "판정: %s (신뢰도 %.0f%%)\n"
        "조사 횟수: %d회\n\n"
        "수집된 증거:\n%s\n\n"
        "위 정보로 보안 분석가용 내러티브를 작성하라."
        % (
            " / ".join(titles) if titles else "관련 finding",
            meta.get("verdict", "inconclusive"),
            meta.get("confidence_score", 0.0) * 100,
            meta.get("tool_calls_count", 0),
            "\n".join(evidence_lines) if evidence_lines else "(증거 없음)",
        )
    )


class BedrockReasoningAgent:
    """LLM이 evidence를 읽고 내러티브를 생성하는 실배포 Reasoning 에이전트.

    risk_level·recommended_actions는 reasoning.py의 결정론적 로직을 그대로 재사용
    (일관성 유지 — LLM은 자연어 설명만 담당).
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        region: str = "ap-northeast-2",
        profile: Optional[str] = None,
    ) -> None:
        self.model_id = model_id
        self.model_label = _short_model_label(model_id)
        # orchestrator가 analyze() 호출 후 읽는 관측용 속성 — BedrockHypothesisAgent와 동일 패턴.
        self.last_tokens = (0, 0)
        try:
            import boto3
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("BedrockReasoningAgent는 boto3 필요 — pip install boto3") from e
        session = boto3.Session(profile_name=profile, region_name=region)
        self._client = session.client("bedrock-runtime")

    def analyze(self, case: dict, findings_map: Dict[str, dict]) -> dict:
        """case(evidence 완료)를 받아 reasoning 결과 딕셔너리를 반환한다(ReasoningAgent와 동일 시그니처)."""
        meta = case.get("evidence_meta", {})
        verdict = meta.get("verdict", "inconclusive")
        confidence = meta.get("confidence_score", 0.0)

        finding_ids = case.get("finding", {}).get("finding_ids", [])
        findings = [findings_map[fid] for fid in finding_ids if fid in findings_map]

        resp = self._client.converse(
            modelId=self.model_id,
            system=[{"text": _SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": _user_prompt(case, findings_map)}]}],
            inferenceConfig={"maxTokens": 512, "temperature": 0.3},
        )
        usage = resp.get("usage") or {}
        self.last_tokens = (usage.get("inputTokens", 0), usage.get("outputTokens", 0))
        narrative_parts = [
            block["text"] for block in resp["output"]["message"]["content"] if "text" in block
        ]
        narrative = "".join(narrative_parts).strip() or (
            "케이스(%s) 판정: %s (신뢰도 %.0f%%)."
            % (", ".join(finding_ids) or "unknown", verdict, confidence * 100)
        )

        return {
            "narrative": narrative,
            "risk_level": _risk_level(verdict, confidence),
            "recommended_actions": _recommended_actions(verdict, findings),
        }
