"""엔진 실 tool-use vertical slice 진입점 — RealToolExecutor + BedrockEvidenceAgent.

이 스크립트가 프로젝트의 심장을 '실제로' 증명한다:
  LLM(Bedrock)이 스스로 read-only API(s3:GetBucketPolicy·GetPublicAccessBlock)를 골라
  실제 AWS 버킷을 조사하고, 응답에 근거해 위험을 판정한다(목업 canned 응답이 아님).

⚠️ 실행 전제 (반드시 준형과 함께 — 비용·격리):
  1) AWS 자격증명: read-only 권한(계약④ allowlist)이 있는 프로파일/역할.
  2) Bedrock 모델 액세스 승인: 콘솔에서 Haiku 모델 액세스 요청(일회성).
  3) 서울 리전 model ID 확정: `aws bedrock list-foundation-models --region ap-northeast-2`
     로 실제 ID/inference profile 확인 후 --model 로 전달(bare name은 404).
  4) infra/slice apply: 조사할 공개 S3 표적이 있어야 함. 테스트 후 즉시 `terraform destroy`.
비용: escalate 소수 × Haiku 토큰 + S3 read-only 몇 회 ≈ 수 센트. (project-draft §22 가드레일)

사용:
  # infra/slice apply 출력에서 버킷명 확인 후
  python -m engine.run_real --resource aws:s3_bucket:<버킷명> [--model <bedrock-model-id>] [--profile <aws-profile>]

목업 데모(인프라·Bedrock 0)는 `python -m engine.run_demo` — 이 스크립트와 별개.
"""
from __future__ import annotations

import argparse
import sys

# 윈도우 콘솔(cp949) 대응 — 한글·기호 출력 크래시 방지(run_demo와 동일).
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from engine.evidence.bedrock_planner import DEFAULT_MODEL_ID, BedrockEvidenceAgent
from engine.evidence.triage import triage
from engine.core.tools import RealToolExecutor


def _slice_finding(resource_id: str) -> dict:
    """slice 표적(공개 S3)에 대한 최소 finding — 정규화부가 없어도 엔진을 돌리기 위한 씨앗.

    실 파이프라인에선 이 finding이 스캐너→정규화부(계약①)에서 흘러온다. 여기선 slice
    검증이 목적이라 손으로 하나 만든다(공개 S3 = INTERNAL-S3-PUBLIC-001).
    """
    return {
        "finding_id": "slice-0000-4000-8000-000000000001",
        "cloud": "aws",
        "resource_id": resource_id,
        "resource_type": "s3_bucket",
        "pillar": "cspm",
        "control_id": "INTERNAL-S3-PUBLIC-001",
        "title": "S3 bucket allows public access (vertical slice target)",
        "severity_id": 1,
        "status": "open",
        "attack_path_id": None,
    }


def _hr(t: str) -> None:
    print("\n" + "=" * 68 + "\n" + t + "\n" + "=" * 68)


def main() -> int:
    ap = argparse.ArgumentParser(description="엔진 실 tool-use vertical slice")
    ap.add_argument("--resource", required=True, help="조사 대상 캐논 resource_id (예: aws:s3_bucket:foo)")
    ap.add_argument("--model", default=DEFAULT_MODEL_ID, help="Bedrock model ID/inference profile")
    ap.add_argument("--region", default="ap-northeast-2")
    ap.add_argument("--profile", default=None, help="AWS 프로파일(선택)")
    args = ap.parse_args()

    finding = _slice_finding(args.resource)

    # ① Triage — 이 finding이 풀 조사로 승급되는지(게이트, 목업과 동일 로직)
    _hr("① 트리아지 게이트")
    tr = triage(finding)
    print("escalate=%s / priority=%.3f / %s" % (tr.escalate, tr.priority_score, tr.reason))
    if not tr.escalate:
        print("escalate 안 됨 — 조사 종료")
        return 0

    # ② Evidence — LLM이 스스로 read-only 툴을 골라 실제 AWS 조사(챗봇 탈출, 실동작)
    _hr("② Evidence — Bedrock LLM이 스스로 read-only 툴 선택·실행 (실 AWS)")
    executor = RealToolExecutor(region=args.region, profile=args.profile)
    agent = BedrockEvidenceAgent(executor, model_id=args.model, region=args.region, profile=args.profile)
    out = agent.investigate([finding])

    print("LLM이 선택한 툴 %d개 (실행 성공 %d회, 미구현/차단은 성공에서 제외):"
          % (len(out.plan), out.tool_calls_count))
    for tool, rid in out.plan:
        print("  → %s  on  %s" % (tool, rid))
    print("\n수집 증거:")
    for e in out.evidence:
        print("  [%s] %s\n       └ %s" % (e.get("ts", ""), e["tool"], e["result_summary"]))
    print("\n판정: %s (신뢰도 %.0f%%)" % (out.verdict.upper(), out.confidence_score * 100))

    # 핵심 성공 기준: LLM이 실제로 툴을 1회 이상 스스로 호출했는가(= tool use 증명)
    proved = out.tool_calls_count >= 1
    _hr("③ 결과")
    print("실 tool-use 증명(LLM이 read-only API 자가 호출): %s" % ("OK ✅" if proved else "실패 ⚠️"))
    return 0 if proved else 1


if __name__ == "__main__":
    raise SystemExit(main())
