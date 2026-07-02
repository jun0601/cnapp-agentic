"""Bedrock LLM tool-use 플래너 (준형 담당) — Evidence '뇌'의 실배포 버전.

`evidence.py`의 규칙 플래너(`PLAN_BY_CONTROL`)는 '어떤 read-only 툴을 호출할지'를
사람이 만든 딕셔너리로 정한다. 여기 `BedrockEvidenceAgent`는 그 결정을 **LLM(Bedrock
Converse tool use)에게 넘긴다** — LLM이 finding을 읽고 스스로 어떤 read-only API를
어느 resource에 호출할지 판단해(가설→증거 수집) 실행기로 호출한다. 이것이 '챗봇 탈출'의
진짜 형태(project-draft §9 UC0 — "LLM이 read-only API를 스스로 호출하는가").

인터페이스는 `EvidenceAgent`와 동일: `investigate(findings) -> EvidenceOutput`.
→ Orchestrator에서 `EvidenceAgent` 대신 이걸 주입하면 조사 로직 스왑(계약이 SSOT).
   규칙 플래너 데모(`engine.run_demo`)는 무변 — 이 파일은 실배포 경로만 추가.

allowlist(계약④)는 **두 겹으로 강제**:
  ① toolConfig inputSchema의 `api` enum = allowlist → LLM이 애초에 그 밖을 못 고름.
  ② `executor._check()` (실제 호출 직전 재확인) → LLM이 우회 시도해도 실행기가 차단.
변경/쓰기 API는 allowlist에 없으므로 어느 쪽으로도 호출 불가(read-only first, 거버넌스 §17).

boto3(bedrock-runtime)는 **지연 import** — 미설치/무자격 환경에서도 이 모듈 import·py_compile은 안전.
실 호출 전제: AWS 자격증명 + Bedrock 모델 액세스 승인 + 정확한 서울 리전 model ID.
"""
from __future__ import annotations

import json
from typing import List, Optional, Tuple

from engine.core.contracts import load_allowlist
from engine.core.tools import ToolExecutor, ToolNotAllowed, ToolResult
from engine.evidence.evidence import EvidenceOutput, _verdict

# ⚠️ 예시 값 — 실제 서울(ap-northeast-2) 가용 model ID/inference profile ARN을
#    `aws bedrock list-foundation-models --region ap-northeast-2` 로 확인 후 확정한다.
#    bare name("claude-haiku-4-5")은 Bedrock에서 404 — date suffix·리전 프로파일 필요.
#    Evidence는 고빈도 분류/tool 라우팅이라 Haiku 티어(project-draft §15).
DEFAULT_MODEL_ID = "apac.anthropic.claude-haiku-4-5-20251001-v1:0"

# LLM tool-use 루프 안전 상한 — 폭주 방지(무한 tool 호출 차단).
MAX_TOOL_ITERATIONS = 6

# Evidence가 LLM에 부여하는 단일 tool. 실제 read-only API는 api enum(=allowlist)으로 고른다.
_TOOL_NAME = "invoke_readonly_api"

_SYSTEM_PROMPT = (
    "너는 클라우드 보안 Evidence 에이전트다. 주어진 finding들의 위험이 실제인지 확인하기 위해, "
    "read-only API를 스스로 골라 호출(tool use)해 증거를 모은다. 규칙:\n"
    "1) 오직 read-only API만 호출한다(allowlist가 강제). 변경/쓰기/삭제는 절대 하지 않는다.\n"
    "2) 각 finding의 resource_id에 대해 위험을 확증/반증할 수 있는 API를 순서대로 호출한다.\n"
    "3) 충분한 증거를 모았다고 판단되면 tool 호출을 멈추고, 무엇을 확인했는지 한국어로 짧게 요약한다.\n"
    "4) 근거 없는 추측 금지 — 판정은 실제 API 응답에만 근거한다."
)


def _tool_config(allowlist: List[str]) -> dict:
    """계약④ allowlist를 Bedrock Converse toolConfig로 변환.

    단일 tool(invoke_readonly_api)의 api enum이 allowlist → LLM이 스키마 레벨에서
    허용된 read-only API만 고를 수 있다(allowlist 1차 강제).
    """
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": _TOOL_NAME,
                    "description": (
                        "리소스 하나에 대해 read-only 클라우드 API 1개를 호출해 증거를 수집한다. "
                        "allowlist에 있는 read-only API만 허용된다."
                    ),
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "api": {
                                    "type": "string",
                                    "enum": allowlist,
                                    "description": "호출할 read-only API (계약④ allowlist)",
                                },
                                "resource_id": {
                                    "type": "string",
                                    "description": "대상 리소스의 캐논 id {cloud}:{type}:{native_id}",
                                },
                            },
                            "required": ["api", "resource_id"],
                        }
                    },
                }
            }
        ]
    }


def _user_prompt(findings: List[dict], hypotheses: Optional[List[str]]) -> str:
    lines = ["다음 finding들의 위험을 read-only API로 조사하라:\n"]
    for f in findings:
        lines.append(
            "- control_id=%s / resource_id=%s / severity_id=%s / %s"
            % (
                f.get("control_id", "?"),
                f.get("resource_id", "?"),
                f.get("severity_id", "?"),
                f.get("title", ""),
            )
        )
    if hypotheses:
        lines.append("\n검증할 가설:")
        for h in hypotheses:
            lines.append("- " + h)
    return "\n".join(lines)


class BedrockEvidenceAgent:
    """LLM이 스스로 read-only 툴을 골라 호출하는 Evidence 에이전트.

    `EvidenceAgent`와 동일 인터페이스(`investigate(findings) -> EvidenceOutput`).
    executor는 목업(MockToolExecutor)이든 실물(RealToolExecutor)이든 무관 —
    LLM이 고른 (api, resource_id)를 executor가 실행(allowlist 2차 강제).
    """

    def __init__(
        self,
        executor: ToolExecutor,
        model_id: str = DEFAULT_MODEL_ID,
        region: str = "ap-northeast-2",
        profile: Optional[str] = None,
        max_iterations: int = MAX_TOOL_ITERATIONS,
    ) -> None:
        self.executor = executor
        self.model_id = model_id
        self.max_iterations = max_iterations
        try:
            import boto3
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("BedrockEvidenceAgent는 boto3 필요 — pip install boto3") from e
        session = boto3.Session(profile_name=profile, region_name=region)
        self._client = session.client("bedrock-runtime")
        al = load_allowlist()
        self._allowlist = list(al["aws"]) + list(al["azure"])
        self._tool_config = _tool_config(self._allowlist)

    def investigate(
        self, findings: List[dict], hypotheses: Optional[List[str]] = None
    ) -> EvidenceOutput:
        """LLM tool-use 루프로 증거 수집. EvidenceOutput(계약②/⑦) 반환."""
        messages = [
            {"role": "user", "content": [{"text": _user_prompt(findings, hypotheses)}]}
        ]
        results: List[ToolResult] = []
        plan: List[Tuple[str, str]] = []

        for _ in range(self.max_iterations):
            resp = self._client.converse(
                modelId=self.model_id,
                system=[{"text": _SYSTEM_PROMPT}],
                messages=messages,
                toolConfig=self._tool_config,
                inferenceConfig={"maxTokens": 1024, "temperature": 0.0},
            )
            out_msg = resp["output"]["message"]
            messages.append(out_msg)

            if resp.get("stopReason") != "tool_use":
                break  # LLM이 조사 종료(end_turn) — 더 볼 게 없다고 판단

            # LLM이 요청한 tool(들) 실행 → toolResult로 되돌려줌(에이전틱 루프)
            tool_results = []
            for block in out_msg.get("content", []):
                tu = block.get("toolUse")
                if not tu:
                    continue
                api = tu["input"]["api"]
                rid = tu["input"]["resource_id"]
                plan.append((api, rid))
                tr, content, status = self._run_tool(api, rid)
                if tr is not None:
                    results.append(tr)
                tool_results.append(
                    {
                        "toolResult": {
                            "toolUseId": tu["toolUseId"],
                            "content": content,
                            "status": status,
                        }
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        confirming = sum(1 for r in results if r.confirms)
        verdict, confidence = _verdict(confirming, len(results))
        return EvidenceOutput(
            evidence=[r.to_evidence_item() for r in results],
            tool_calls_count=len(results),
            confidence_score=confidence,
            verdict=verdict,
            plan=plan,
        )

    def _run_tool(self, api: str, resource_id: str):
        """LLM이 고른 (api, resource_id) 실행. allowlist/미구현은 error toolResult로 되돌림.

        반환: (ToolResult|None, converse content[], status)
        - 정상: ToolResult + json content + "success"
        - 차단/미구현: None + text content + "error" (LLM이 다음 수를 조정하게)
        """
        try:
            r = self.executor.execute(api, resource_id)  # ★ allowlist 2차 강제(executor._check)
        except ToolNotAllowed as e:
            return None, [{"text": "차단: " + str(e)}], "error"
        except NotImplementedError as e:
            return None, [{"text": "미구현: " + str(e)}], "error"
        content = [
            {"json": {"summary": r.result_summary, "confirms": r.confirms, "raw": r.raw}}
        ]
        return r, content, "success"
