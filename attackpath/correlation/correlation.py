"""Correlation engine (진우 담당) — R1~R5 규칙으로 finding → attack-path 그래프 생성.

목업: control_id 패턴 매칭 기반 rule-based 상관.
실배포 스왑: correlate() 인터페이스 유지, findings 파라미터를 DB 쿼리 결과로 교체.
출력: 계약③ attack-path.schema.json 준수.
"""
from __future__ import annotations

from typing import Dict, List, Optional

# ── R1~R5 트리거 control_id (project-draft §4.4) ──────────────────────────────
_R1_KEV       = "INTERNAL-VULN-KEV-001"            # KEV-listed 취약 워크로드
_R1_SG        = "INTERNAL-SG-OPEN-INGRESS-001"     # 그 워크로드를 외부 노출시키는 SG
_R2_OVERPRIV  = "INTERNAL-IAM-OVERPRIV-001"        # 워크로드에 붙은 과도 IAM/IRSA
_R3_PLAINTEXT = "INTERNAL-SECRET-PLAINTEXT-001"    # 평문 Azure 자격증명 (AWS side)
_R3_AZURE_SP  = "INTERNAL-ENTRA-SP-CRED-001"       # 만료 없는 Azure SP (Azure side)
_R4_S3_PUBLIC = "INTERNAL-S3-PUBLIC-001"           # public S3 버킷
_R4_PII       = "INTERNAL-DATA-PII-EXPOSED-001"    # 동일 버킷 PII 노출
_R5_ENTRA_APP = frozenset({                         # Entra 과도권한 앱 등록
    "INTERNAL-ENTRA-OVERPRIV-APP-001",
    "INTERNAL-ENTRA-INSECURE-CFG-001",
})

# mock-attack-paths.json 골든 경로 ID (2-pass: 1차 상관이 이 ID를 부여)
_GOLDEN_PATH_ID = "a0000000-0000-4000-8000-000000000001"

# 체인 노드 수 >= 이 값이면 severity Critical(1) 격상
_CRITICAL_CHAIN_LEN = 3


def _first(findings: List[dict], *ctrl_ids: str) -> Optional[dict]:
    """control_id가 일치하는 첫 번째 finding 반환."""
    for f in findings:
        if f.get("control_id") in ctrl_ids:
            return f
    return None


def _node(nid: str, cloud: str, resource_id: str, label: str, pillar: str) -> dict:
    return {"id": nid, "cloud": cloud, "resource_id": resource_id,
            "label": label, "pillar": pillar}


def _edge(from_id: str, to_id: str, etype: str, cross_cloud: bool, label: str) -> dict:
    return {"from": from_id, "to": to_id, "type": etype,
            "cross_cloud": cross_cloud, "label": label}


def _try_golden_chain(findings: List[dict]) -> Optional[dict]:
    """R1~R5 골든 체인 시도. 5개 규칙 전부 발화하면 attack_path dict 반환, 아니면 None."""

    # ── R1: KEV 취약 워크로드 + 외부 노출 SG (토폴로지 인접 — 파드↔부착 SG)
    # 목업: 같은 AWS 컨텍스트에 두 finding이 존재하면 인접으로 간주.
    # 실배포: 파드→ENI→SG 매핑 테이블로 실제 부착 관계 확인.
    r1_kev = _first(findings, _R1_KEV)
    r1_sg  = _first(findings, _R1_SG)
    if not r1_kev or not r1_sg:
        return None

    # ── R2: 그 워크로드에 붙은 과도 IAM/IRSA 권한
    r2 = _first(findings, _R2_OVERPRIV)
    if not r2:
        return None

    # ── R3: 평문 Azure 자격증명(AWS side) + 해당 Azure SP finding(Azure side)
    r3_aws   = _first(findings, _R3_PLAINTEXT)
    r3_azure = _first(findings, _R3_AZURE_SP)
    if not r3_aws or not r3_azure:
        return None

    # ── R4: 과도 권한이 닿는 S3에 public + PII — 같은 버킷이어야 체인 성립
    r4_s3  = _first(findings, _R4_S3_PUBLIC)
    r4_pii = _first(findings, _R4_PII)
    if not r4_s3 or not r4_pii:
        return None
    if r4_s3.get("resource_id") != r4_pii.get("resource_id"):
        return None  # R4: 다른 버킷이면 미발화

    # ── R5: 탈취 Azure 자격증명 + Entra 과도권한 App Registration
    r5 = _first(findings, *_R5_ENTRA_APP)
    if not r5:
        return None

    # ── 노드 조립 ────────────────────────────────────────────────────────────
    nodes = [
        _node("n1", "aws",   r1_kev["resource_id"],   "product 취약 이미지(KEV CVE)",    "vuln"),
        _node("n2", "aws",   r2["resource_id"],        "order 과도 IRSA 권한(s3:*)",      "ciem"),
        _node("n3", "aws",   r4_s3["resource_id"],    "member 공개 S3 + 회원 PII",        "data"),
        _node("n4", "azure", r3_azure["resource_id"], "탈취된 Azure SP 자격증명",          "ciem"),
        _node("n5", "azure", r5["resource_id"],        "과도권한 App Registration",        "ciem"),
    ]

    # ── 엣지 조립 ────────────────────────────────────────────────────────────
    edges = [
        _edge("n1", "n2", "lateral_move",     False,
              "product 침투 → order 과도 IRSA 권한 탈취"),
        _edge("n2", "n3", "data_exfil",       False,
              "s3:* 권한으로 member 공개 S3의 PII 탈취"),
        _edge("n2", "n4", "credential_theft", True,
              "order 평문 시크릿의 Azure 자격증명으로 클라우드 경계 횡단"),
        _edge("n4", "n5", "identity_takeover", False,
              "탈취 자격증명으로 과도권한 App Registration 장악 → 디렉터리 전체 통제권"),
    ]

    # 체인 길이 >= 3 → severity Critical 격상
    severity_id = 1 if len(nodes) >= _CRITICAL_CHAIN_LEN else 2

    chain_findings = [r1_kev, r1_sg, r2, r3_aws, r3_azure, r4_s3, r4_pii, r5]
    finding_ids = [f["finding_id"] for f in chain_findings if f and "finding_id" in f]

    return {
        "attack_path_id": _GOLDEN_PATH_ID,
        "severity_id":    severity_id,
        "nodes":          nodes,
        "edges":          edges,
        "finding_ids":    finding_ids,
        "narrative_text": (
            "공격자가 product의 취약 이미지(KEV CVE)로 침투해 order 파드의 과도 IRSA 권한을 탈취(측면 이동)하고, "
            "그 권한으로 member의 공개 S3 버킷에서 회원 PII를 탈취했다. 동시에 order 파드 평문 시크릿에 "
            "노출된 Azure 자격증명으로 클라우드 경계를 넘어, Azure Entra ID의 과도권한 App Registration을 "
            "장악해 디렉터리 전체 통제권을 확보했다. 단일 finding은 각각 중간 위험이나, "
            "묶이면 AWS 워크로드->Azure 신원을 가로지르는 Critical 탈취 경로가 된다."
        ),
    }


def _backfill(findings: List[dict], finding_ids: List[str], path_id: str) -> None:
    """2-pass: 1차 상관 완료 후 해당 finding에 attack_path_id 역주입.

    cnapp.attackpath.correlation.completed 이벤트 발행 전 DB upsert와 동일한 역할.
    """
    id_set = set(finding_ids)
    for f in findings:
        if f.get("finding_id") in id_set:
            f["attack_path_id"] = path_id


class CorrelationEngine:
    """R1~R5 규칙으로 finding 묶음 -> attack-path 그래프[] 생성.

    실배포 스왑:
      - correlate()의 findings 파라미터를 RDS finding 조회 결과로 교체
      - _backfill() 대신 RDS UPDATE attack_path_id 실행
    출력 구조는 계약 3(attack-path.schema.json) 준수.
    """

    def correlate(self, findings: List[dict]) -> List[dict]:
        """findings 목록 -> attack_path 그래프 목록(계약 3 JSON array)."""
        paths = []  # type: List[dict]

        golden = _try_golden_chain(findings)
        if golden:
            paths.append(golden)
            _backfill(findings, golden["finding_ids"], golden["attack_path_id"])

        return paths
