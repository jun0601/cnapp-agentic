"""attack-path 그래프 데이터 모델 (준형 담당) — 계약③ SSOT.

노드·엣지·그래프의 '형태'와 '불변식'을 한 곳에 정의한다. 상관 로직(correlation, 진우)이
이 모델로 그래프를 조립하고, 콘솔(React Flow)이 to_dict() 출력을 렌더한다.
계약③(contracts/attack-path.schema.json)과 1:1 — 필드·enum이 스키마를 그대로 반영.

그래프 '형태'는 데이터 소스와 독립 → 목업/실배포 무관(모델 재사용).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

# ── 계약③ enum (스키마 properties와 동일하게 유지) ────────────────────────────
CLOUDS = frozenset({"aws", "azure"})
PILLARS = frozenset({"cspm", "ciem", "vuln", "kspm", "data", "attack_path"})
EDGE_TYPES = frozenset({"lateral_move", "credential_theft", "data_exfil", "identity_takeover"})

# 체인 노드 수 >= 이 값이면 severity Critical(1) 격상 — 독성 조합(계약③ severity_id 설명)
CRITICAL_CHAIN_LEN = 3


@dataclass
class Node:
    """attack-path 그래프 노드 — 침해 자산 하나(계약③ nodes[])."""

    id: str
    cloud: str          # aws | azure
    resource_id: str    # finding.resource_id와 동일 캐논(4.4.1a)
    label: str
    pillar: str         # cspm | ciem | vuln | kspm | data | attack_path

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "cloud": self.cloud,
            "resource_id": self.resource_id,
            "label": self.label,
            "pillar": self.pillar,
        }


@dataclass
class Edge:
    """attack-path 그래프 엣지 — 공격 이동 하나(계약③ edges[]).

    from_id/to_id → to_dict()에서 계약 키 'from'/'to'로 매핑(파이썬 예약어 회피).
    """

    from_id: str
    to_id: str
    type: str                    # lateral_move | credential_theft | data_exfil | identity_takeover
    cross_cloud: bool = False    # AWS↔Azure 경계 횡단 — 콘솔 강조 렌더 트리거
    label: str = ""

    def to_dict(self) -> dict:
        return {
            "from": self.from_id,
            "to": self.to_id,
            "type": self.type,
            "cross_cloud": self.cross_cloud,
            "label": self.label,
        }


@dataclass
class AttackPathGraph:
    """계약③ attack-path 그래프 컨테이너 — 상관 로직이 조립, 콘솔이 렌더.

    add_node/add_edge로 조립 → validate_graph()로 불변식 검사 → to_dict()로 계약③ 직렬화.
    finding_ids는 2-pass backfill용 provenance(어떤 finding이 이 경로를 구성했나) —
    계약③ 스키마엔 없는 필드라 to_dict()에서 제외한다(additionalProperties:false 준수).
    """

    attack_path_id: str
    narrative_text: str = ""
    severity_id: int = 2
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    finding_ids: List[str] = field(default_factory=list)  # backfill용 — 직렬화 제외

    def add_node(self, node: Node) -> "AttackPathGraph":
        self.nodes.append(node)
        return self

    def add_edge(self, edge: Edge) -> "AttackPathGraph":
        self.edges.append(edge)
        return self

    def apply_chain_severity(self) -> "AttackPathGraph":
        """노드 수 기반 severity 격상(체인>=3 → Critical). 조립 완료 후 호출."""
        self.severity_id = 1 if len(self.nodes) >= CRITICAL_CHAIN_LEN else 2
        return self

    def to_dict(self) -> dict:
        """계약③(attack-path.schema.json) 준수 dict — finding_ids 제외."""
        return {
            "attack_path_id": self.attack_path_id,
            "severity_id": self.severity_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "narrative_text": self.narrative_text,
        }


def validate_graph(graph: AttackPathGraph) -> List[str]:
    """그래프 불변식 검사 — 계약③ 정합 + 구조 무결성. 오류 목록 반환(빈 리스트=OK).

    검사 항목:
      - severity_id 범위(1~5)
      - node.cloud/pillar enum, id·resource_id 필수, node.id 유일성
      - edge.type enum, from/to가 실존 노드 참조
      - cross_cloud 플래그 ↔ 실제 클라우드 경계 횡단 여부 일치
    """
    errs: List[str] = []

    if not (1 <= graph.severity_id <= 5):
        errs.append("severity_id 범위 위반(1~5): %s" % graph.severity_id)

    node_ids = set()          # type: ignore[var-annotated]
    node_cloud: Dict[str, str] = {}
    for i, n in enumerate(graph.nodes):
        if n.cloud not in CLOUDS:
            errs.append("nodes[%d].cloud enum 위반: %s" % (i, n.cloud))
        if n.pillar not in PILLARS:
            errs.append("nodes[%d].pillar enum 위반: %s" % (i, n.pillar))
        if not n.id or not n.resource_id:
            errs.append("nodes[%d] id/resource_id 필수" % i)
        if n.id in node_ids:
            errs.append("nodes[%d].id 중복: %s" % (i, n.id))
        node_ids.add(n.id)
        node_cloud[n.id] = n.cloud

    for i, e in enumerate(graph.edges):
        if e.type not in EDGE_TYPES:
            errs.append("edges[%d].type enum 위반: %s" % (i, e.type))
        if e.from_id not in node_ids:
            errs.append("edges[%d].from 미존재 노드 참조: %s" % (i, e.from_id))
        if e.to_id not in node_ids:
            errs.append("edges[%d].to 미존재 노드 참조: %s" % (i, e.to_id))
        # cross_cloud 플래그가 실제 경계 횡단과 맞는지(양끝 노드가 모두 존재할 때만)
        if e.from_id in node_cloud and e.to_id in node_cloud:
            crosses = node_cloud[e.from_id] != node_cloud[e.to_id]
            if crosses != e.cross_cloud:
                errs.append(
                    "edges[%d].cross_cloud=%s 인데 실제 %s→%s (경계횡단=%s)"
                    % (i, e.cross_cloud, node_cloud[e.from_id], node_cloud[e.to_id], crosses)
                )

    return errs
