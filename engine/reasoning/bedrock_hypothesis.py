"""Hypothesis 에이전트 실배포판 — Bedrock LLM 호출로 가설 생성.

`hypothesis.py`의 `HypothesisAgent`(control_id→템플릿 딕셔너리)를 **Bedrock Claude Haiku
호출로 교체**한다 — 문서화된 "실배포 스왑: generate() 내부 템플릿 로직을 Bedrock Haiku LLM
호출로 교체"(hypothesis.py 상단 docstring)를 실제로 구현한 것.

인터페이스는 `HypothesisAgent`와 동일: `generate(findings, paths) -> List[str]`.
→ Orchestrator에 `hypothesis_agent=BedrockHypothesisAgent()`로 주입하면 스왑(계약 무변,
   `HypothesisAgent` 템플릿 데모는 그대로 유지).

구조화 출력 강제: Converse `toolChoice={"tool": {"name": ...}}`로 LLM이 반드시
`submit_hypotheses` 툴 1회를 호출하게 만든다 — Evidence(bedrock_planner.py)처럼 여러 턴
도는 tool-use 루프가 필요 없다(가설 생성은 read-only API 호출이 아니라 순수 텍스트 추론이라
"제출" 툴 하나로 구조화된 응답만 받으면 충분). 자유형 텍스트 파싱보다 신뢰도가 높다.

boto3는 지연 import — 미설치/무자격 환경에서도 이 모듈 import·py_compile은 안전.
"""
from __future__ import annotations

import json
from typing import List, Optional

# Hypothesis는 저빈도(케이스당 1회) 가설 생성이라 Haiku 티어(project-draft §15).
DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"

_TOOL_NAME = "submit_hypotheses"


def _short_model_label(model_id: str) -> str:
    """model_trace에 남길 짧은 티어 라벨 — inference profile 전체 ARN 문자열 대신
    "haiku"/"sonnet" 같이 사람이 바로 읽는 이름으로(모델이 바뀌어도 라벨은 실제 사용값 반영)."""
    m = model_id.lower()
    if "haiku" in m:
        return "haiku"
    if "sonnet" in m:
        return "sonnet"
    return model_id

_SYSTEM_PROMPT = (
    "너는 클라우드 보안 위협 헌팅 에이전트다. 승급된(escalated) finding들과 attack-path "
    "그래프를 보고, Evidence 에이전트가 read-only API로 검증할 수 있는 **구체적이고 "
    "검증 가능한** 한국어 가설 문장을 만든다. 규칙:\n"
    "1) 각 가설은 특정 resource_id를 언급하고, '~하면 ~할 수 있다' 형태로 조건-결과를 명시한다.\n"
    "2) attack-path에 클라우드 경계를 넘는(cross_cloud) 엣지가 있으면, 그 경계를 넘는 "
    "크로스클라우드 체인 가설을 반드시 하나 포함한다.\n"
    "3) 근거 없는 추측 금지 — finding에 실제로 있는 정보만 근거로 삼는다.\n"
    "4) 가설은 최소 1개, 최대 5개."
)


def _tool_config() -> dict:
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": _TOOL_NAME,
                    "description": "검증할 공격 가설 목록을 제출한다.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "hypotheses": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "한국어 가설 문장 목록",
                                }
                            },
                            "required": ["hypotheses"],
                        }
                    },
                }
            }
        ],
        "toolChoice": {"tool": {"name": _TOOL_NAME}},
    }


def _user_prompt(findings: List[dict], paths: List[dict]) -> str:
    lines = ["escalated finding 목록:"]
    for f in findings:
        lines.append(
            "- control_id=%s / resource_id=%s / severity_id=%s / %s"
            % (f.get("control_id", "?"), f.get("resource_id", "?"),
               f.get("severity_id", "?"), f.get("title", ""))
        )
    if paths:
        lines.append("\nattack-path 그래프:")
        for p in paths:
            for e in p.get("edges", []):
                lines.append(
                    "- edge type=%s cross_cloud=%s (%s → %s)"
                    % (e.get("type"), e.get("cross_cloud"), e.get("source"), e.get("target"))
                )
    lines.append("\n위 정보로 검증 가설 목록을 submit_hypotheses 툴로 제출하라.")
    return "\n".join(lines)


class BedrockHypothesisAgent:
    """LLM이 finding·attack-path를 읽고 검증 가설을 생성하는 실배포 Hypothesis 에이전트."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        region: str = "ap-northeast-2",
        profile: Optional[str] = None,
    ) -> None:
        self.model_id = model_id
        self.model_label = _short_model_label(model_id)
        # orchestrator가 generate() 호출 후 읽는 관측용 속성(계약 밖) — HypothesisAgent와
        # 동일 이름이라 mock↔real 어느 쪽이든 getattr(agent, "last_tokens", (0,0))로 동일하게 읽힘.
        self.last_tokens = (0, 0)
        try:
            import boto3
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("BedrockHypothesisAgent는 boto3 필요 — pip install boto3") from e
        session = boto3.Session(profile_name=profile, region_name=region)
        self._client = session.client("bedrock-runtime")

    def generate(self, findings: List[dict], paths: List[dict]) -> List[str]:
        """finding 목록과 attack_path에서 검증 가설 목록을 생성한다(HypothesisAgent와 동일 시그니처)."""
        if not findings:
            self.last_tokens = (0, 0)
            return ["escalated finding의 위험이 실제 환경에서도 재현 가능한지 확인이 필요하다"]

        resp = self._client.converse(
            modelId=self.model_id,
            system=[{"text": _SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": _user_prompt(findings, paths)}]}],
            toolConfig=_tool_config(),
            inferenceConfig={"maxTokens": 1024, "temperature": 0.2},
        )
        usage = resp.get("usage") or {}
        self.last_tokens = (usage.get("inputTokens", 0), usage.get("outputTokens", 0))
        for block in resp["output"]["message"]["content"]:
            tu = block.get("toolUse")
            if tu and tu.get("name") == _TOOL_NAME:
                hyps = tu["input"].get("hypotheses") or []
                if hyps:
                    return [str(h) for h in hyps]
        # LLM이 (드물게) 강제 툴 호출을 안 지켰을 때의 안전망 — 조사 자체는 계속 진행되게.
        return ["escalated finding의 위험이 실제 환경에서도 재현 가능한지 확인이 필요하다"]
