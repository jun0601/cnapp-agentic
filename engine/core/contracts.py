"""계약 로딩 — contracts/*.json을 읽어 엔진에 공급(단일 진실 공급원).

목업 단계: mock-findings/mock-attack-paths를 입력으로 씀. 실배포: 정규화부(pipeline)가
RDS에 넣은 findings를 읽는 어댑터로 교체(계약 스키마 동일 → 코드 무변).
"""
from __future__ import annotations

import json
import os
from typing import Dict, List

_CONTRACTS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "contracts"))


def _load(name: str) -> dict:
    with open(os.path.join(_CONTRACTS_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def load_findings() -> List[dict]:
    """계약① finding[] (목업)."""
    return _load("mock-findings.json")["findings"]


def load_attack_paths() -> List[dict]:
    """계약③ attack_path[] (목업)."""
    return _load("mock-attack-paths.json")["attack_paths"]


def load_allowlist() -> Dict[str, List[str]]:
    """계약④ Evidence read-only 툴 allowlist."""
    data = _load("evidence-allowlist.json")
    return {"aws": data["aws"], "azure": data["azure_ms_graph"]}


def load_control_catalog() -> Dict[str, dict]:
    """4.4.1(b) INTERNAL control 카탈로그."""
    return _load("control-catalog.json")["controls"]


def findings_by_id(findings: List[dict]) -> Dict[str, dict]:
    return {f["finding_id"]: f for f in findings}
