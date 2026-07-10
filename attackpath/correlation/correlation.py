"""Correlation engine (진우 담당) — R1~R5 규칙으로 finding → attack-path 그래프[] 생성.

목업: control_id 패턴 매칭 기반 rule-based 상관.
실배포 스왑: correlate() 인터페이스 유지, findings 파라미터를 DB 쿼리 결과로 교체.
출력: 계약③ attack-path.schema.json 준수.

멀티 경로(2026-07-10): 하나의 posture(현재 finding 집합)에서 **독립적인 공격 경로 여러 개**를
발견한다 — 각 경로 빌더가 자기 조건이 맞을 때만 발화(all-or-nothing이 아니라 발화한 만큼 반환).
결함 토글을 켜면 경로가 늘고, remediation으로 finding이 사라지면 그 경로도 리스트에서 빠진다
(콘솔이 위험도순 리스트로 렌더). 경로끼리 finding을 공유할 수 있고(하나의 미스컨피그가 여러
경로에 참여 — 실제 CNAPP도 동일), attack_path_id는 단일값이라 각 finding은 자신이 속한
**가장 위험도 높은 경로**에 귀속시킨다(_backfill_multi).
"""
from __future__ import annotations

from typing import List, Optional

from attackpath.model.graph import AttackPathGraph, Edge, Node, validate_graph

# ── R1~R5 트리거 control_id (project-draft §4.4) ──────────────────────────────
_R1_KEV       = "INTERNAL-VULN-KEV-001"            # KEV-listed 취약 워크로드
_R1_SG        = "INTERNAL-SG-OPEN-INGRESS-001"     # 그 워크로드를 외부 노출시키는 SG
_R2_OVERPRIV  = "INTERNAL-IAM-OVERPRIV-001"        # 워크로드에 붙은 과도 IAM/IRSA
_R3_PLAINTEXT = "INTERNAL-SECRET-PLAINTEXT-001"    # 평문 Azure 자격증명 (AWS side)
_R3_AZURE_SP  = "INTERNAL-ENTRA-SP-CRED-001"       # 만료 없는 Azure SP (Azure side)
_R4_S3_PUBLIC = "INTERNAL-S3-PUBLIC-001"           # public S3 버킷
_R4_PII       = "INTERNAL-DATA-PII-EXPOSED-001"    # 동일 버킷 PII 노출
_R5_CONSENT      = "INTERNAL-ENTRA-RISKY-CONSENT-001"    # Entra 위험 admin consent
_R5_OVERPRIV_APP = "INTERNAL-ENTRA-OVERPRIV-APP-001"     # Entra 과도권한 앱(Directory.ReadWrite.All) — 노드 지목용
_R5_ENTRA_APP = frozenset({                              # Entra 앱 등록 결함(폴백용 — overpriv 없으면 insecure-cfg)
    _R5_OVERPRIV_APP,
    "INTERNAL-ENTRA-INSECURE-CFG-001",
})

# 경로별 고정 ID (mock-attack-paths.json과 동일 — 2-pass: 1차 상관이 이 ID를 부여)
_HERO_PATH_ID     = "a0000000-0000-4000-8000-000000000001"  # 크로스클라우드 hero
_AWS_DATA_PATH_ID = "a0000000-0000-4000-8000-000000000002"  # AWS 단독 데이터 탈취
_AZURE_ID_PATH_ID = "a0000000-0000-4000-8000-000000000003"  # Azure 단독 신원 장악


def _first(findings: List[dict], *ctrl_ids: str) -> Optional[dict]:
    """control_id가 일치하는 첫 번째 finding 반환."""
    for f in findings:
        if f.get("control_id") in ctrl_ids:
            return f
    return None


def _first_matching(findings: List[dict], ctrl_ids: frozenset, resource_substr: str) -> Optional[dict]:
    """control_id 일치 + resource_id에 특정 문자열을 포함하는 첫 finding(같은 control이 여러
    리소스에 걸릴 때 원하는 리소스를 지목 — 예: 열린 SG가 product·order 둘 다인데 order만 필요)."""
    for f in findings:
        if f.get("control_id") in ctrl_ids and resource_substr in (f.get("resource_id") or ""):
            return f
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  경로 빌더 — 각자 독립. 자기 조건이 다 맞으면 AttackPathGraph, 아니면 None.
#  노드·엣지 조립은 그래프 데이터 모델(model/graph.py, 준형)을 쓴다.
# ══════════════════════════════════════════════════════════════════════════════

def _build_hero(findings: List[dict]) -> Optional[AttackPathGraph]:
    """경로 A (hero) — R1~R5 크로스클라우드 골든 체인. 5개 규칙 전부 발화 시 5노드 그래프.

    product 취약 이미지 → order 과도 IRSA → member 공개 S3 PII + (평문 시크릿의 Azure
    자격증명으로 경계 횡단) → Entra 과도권한 App 장악. AWS 워크로드→Azure 신원을 가로지름.
    """
    # ── R1: KEV 취약 워크로드 + 외부 노출 SG (토폴로지 인접 — 파드↔부착 SG)
    # 목업: 같은 AWS 컨텍스트에 두 finding이 존재하면 인접으로 간주.
    # 실배포: 파드→ENI→SG 매핑 테이블로 실제 부착 관계 확인.
    r1_kev = _first(findings, _R1_KEV)
    r1_sg  = _first(findings, _R1_SG)
    if not r1_kev or not r1_sg:
        return None

    # ── R2: 그 워크로드에 붙은 과도 IAM/IRSA 권한(order-irsa — s3:* 와일드카드)
    # 실 RDS는 ORDER BY 없이 조회라 IAM-OVERPRIV finding이 여러 개(order·member·ci-deploy)면
    # _first()가 임의 순서로 엉뚱한 역할을 집을 수 있음 → order-irsa를 명시적으로 지목(mock의
    # `order-irsa`·라이브의 `...-target-order-irsa` 둘 다 매칭), 없으면 첫 overpriv로 폴백.
    r2 = _first_matching(findings, frozenset({_R2_OVERPRIV}), "order-irsa") or _first(findings, _R2_OVERPRIV)
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
    # IRSA와 같은 이유(실 RDS 무순서 조회) — 과도권한 앱을 명시 지목, 없으면 다른 앱 결함으로 폴백.
    r5 = _first(findings, _R5_OVERPRIV_APP) or _first(findings, *_R5_ENTRA_APP)
    if not r5:
        return None

    # ── 그래프 조립 (model/graph.py — 노드·엣지 형태는 모델 소유) ─────────────
    graph = AttackPathGraph(
        attack_path_id=_HERO_PATH_ID,
        narrative_text=(
            "공격자가 product의 취약 이미지(KEV CVE)로 침투해 order 파드의 과도 IRSA 권한을 탈취(측면 이동)하고, "
            "그 권한으로 member의 공개 S3 버킷에서 회원 PII를 탈취했다. 동시에 order 파드 평문 시크릿에 "
            "노출된 Azure 자격증명으로 클라우드 경계를 넘어, Azure Entra ID의 과도권한 App Registration을 "
            "장악해 디렉터리 전체 통제권을 확보했다. 단일 finding은 각각 중간 위험이나, "
            "묶이면 AWS 워크로드->Azure 신원을 가로지르는 Critical 탈취 경로가 된다."
        ),
    )
    for node in (
        Node("n1", "aws",   r1_kev["resource_id"],   "product 취약 이미지(KEV CVE)", "vuln"),
        Node("n2", "aws",   r2["resource_id"],       "order 과도 IRSA 권한(s3:*)",   "ciem"),
        Node("n3", "aws",   r4_s3["resource_id"],    "member 공개 S3 + 회원 PII",     "data"),
        Node("n4", "azure", r3_azure["resource_id"], "탈취된 Azure SP 자격증명",       "ciem"),
        # n5 pillar는 하드코딩하지 않고 매칭된 finding에서 도출 — _R5_ENTRA_APP이 pillar가
        # 다른 control 2종(ciem·cspm, control-catalog.json)을 매칭 대상으로 두는데, _first()가
        # 순서 의존이라 어느 쪽이 먼저 매칭되든 그래프 노드가 항상 실제 finding의 pillar를
        # 반영하게 함(2026-07-03 재검증 — 하드코딩 시 실 DB 쿼리 순서에 따라 그래프 pillar가
        # 실제 finding과 불일치할 수 있었음, validate_graph는 enum만 체크해서 못 잡던 버그).
        Node("n5", "azure", r5["resource_id"],       "과도권한 App Registration",     r5.get("pillar", "ciem")),
    ):
        graph.add_node(node)
    for edge in (
        Edge("n1", "n2", "lateral_move",     False, "product 침투 → order 과도 IRSA 권한 탈취"),
        Edge("n2", "n3", "data_exfil",       False, "s3:* 권한으로 member 공개 S3의 PII 탈취"),
        Edge("n2", "n4", "credential_theft", True,  "order 평문 시크릿의 Azure 자격증명으로 클라우드 경계 횡단"),
        Edge("n4", "n5", "identity_takeover", False, "탈취 자격증명으로 과도권한 App Registration 장악 → 디렉터리 전체 통제권"),
    ):
        graph.add_edge(edge)

    graph.apply_chain_severity()  # 체인 길이 >= 3 → Critical(1) 격상

    # 2-pass backfill용 provenance(계약③ 직렬화엔 미포함 — to_dict()가 제외)
    chain_findings = [r1_kev, r1_sg, r2, r3_aws, r3_azure, r4_s3, r4_pii, r5]
    graph.finding_ids = [f["finding_id"] for f in chain_findings if f and "finding_id" in f]

    return graph


def _build_aws_data_exfil(findings: List[dict]) -> Optional[AttackPathGraph]:
    """경로 B (AWS 단독) — 과도 IRSA가 공개 S3의 PII에 직접 닿는 데이터 탈취 경로.

    hero의 Azure 크로스클라우드 구간이 차단돼도, AWS 내부만으로 회원 PII가 노출됨을 보여준다.
    외부 노출된 order 워크로드(SSH 0.0.0.0/0)를 진입점으로 잡아 3노드로 구성(진입점 SG가 없으면
    2노드로 축소 — 견고성). 같은 IRSA·S3 finding을 hero와 공유하지만(한 미스컨피그가 여러 경로에
    참여, realistic), 진입점·서사가 다른 별개 경로다.
    """
    irsa   = _first_matching(findings, frozenset({_R2_OVERPRIV}), "order-irsa") or _first(findings, _R2_OVERPRIV)
    s3     = _first(findings, _R4_S3_PUBLIC)
    pii    = _first(findings, _R4_PII)
    if not irsa or not s3 or not pii:
        return None
    if s3.get("resource_id") != pii.get("resource_id"):
        return None  # 공개+PII가 다른 버킷이면 미발화

    graph = AttackPathGraph(
        attack_path_id=_AWS_DATA_PATH_ID,
        narrative_text=(
            "인터넷에 개방된 order 워크로드(SSH 0.0.0.0/0)를 통해 침투한 공격자는 order IRSA의 "
            "s3:* 와일드카드 권한을 획득해, 크로스클라우드 피벗 없이도 공개된 member 버킷의 회원 "
            "PII를 직접 탈취할 수 있다. hero 경로의 Azure 구간이 차단되더라도 이 AWS 단독 경로만으로 "
            "데이터는 여전히 노출된다 — 과도 IRSA와 공개 버킷 각각을 독립적으로도 조치해야 하는 이유다."
        ),
    )

    sg = _first_matching(findings, frozenset({_R1_SG}), "order")  # order SSH SG(진입점, 있으면 3노드)
    if sg:
        for node in (
            Node("b1", "aws", sg["resource_id"],   "order SSH 0.0.0.0/0 외부 노출", "cspm"),
            Node("b2", "aws", irsa["resource_id"], "order 과도 IRSA(s3:*)",         "ciem"),
            Node("b3", "aws", s3["resource_id"],   "member 공개 S3 + 회원 PII",     "data"),
        ):
            graph.add_node(node)
        graph.add_edge(Edge("b1", "b2", "lateral_move", False, "인터넷 개방 SSH로 order 파드 침투 → IRSA 권한 획득"))
        graph.add_edge(Edge("b2", "b3", "data_exfil",   False, "s3:* 와일드카드로 공개 member 버킷의 회원 PII 직접 탈취"))
        chain = [sg, irsa, s3, pii]
    else:
        for node in (
            Node("b1", "aws", irsa["resource_id"], "order 과도 IRSA(s3:*)",     "ciem"),
            Node("b2", "aws", s3["resource_id"],   "member 공개 S3 + 회원 PII", "data"),
        ):
            graph.add_node(node)
        graph.add_edge(Edge("b1", "b2", "data_exfil", False, "s3:* 와일드카드로 공개 member 버킷의 회원 PII 직접 탈취"))
        chain = [irsa, s3, pii]

    graph.apply_chain_severity()
    graph.finding_ids = [f["finding_id"] for f in chain if f and "finding_id" in f]
    return graph


def _build_azure_identity(findings: List[dict]) -> Optional[AttackPathGraph]:
    """경로 D (Azure 단독) — AWS 침해와 무관하게 Azure 신원 평면만으로 성립하는 디렉터리 장악.

    장기 유효 SP 자격증명이 유출되면 과도권한(Directory.ReadWrite.All) App Registration을
    장악해 Entra 디렉터리 전체 통제권을 얻는다. hero의 Azure 꼬리(SP·App)와 finding을 공유하나,
    "AWS를 전혀 건드리지 않고도 신원 평면만으로 도달 가능"하다는 별개 서사 — Azure 신원 위생을
    독립적으로도 챙겨야 함을 보여준다.
    """
    sp  = _first(findings, _R3_AZURE_SP)                                          # 장기 유효 SP 자격증명
    app = _first(findings, _R5_OVERPRIV_APP) or _first(findings, *_R5_ENTRA_APP)  # 과도권한 App Registration(명시 지목)
    if not sp or not app:
        return None

    consent = _first(findings, _R5_CONSENT)       # 위험 admin consent(있으면 provenance로 가중)

    graph = AttackPathGraph(
        attack_path_id=_AZURE_ID_PATH_ID,
        narrative_text=(
            "AWS 침해와 무관하게 Azure 내부만으로 성립하는 신원 탈취 경로. 24개월 유효한 서비스 주체(SP) "
            "자격증명이 유출되면 과도권한(Directory.ReadWrite.All) App Registration을 장악해 Entra 디렉터리 "
            "전체 통제권을 얻는다. 대상 앱에는 위험한 admin consent도 부여돼 있어 위험이 가중된다. "
            "AWS 워크로드를 전혀 거치지 않고도 신원 평면만으로 도달 가능하다."
        ),
    )
    for node in (
        Node("d1", "azure", sp["resource_id"],  "장기 유효 SP 자격증명(24개월)", sp.get("pillar", "ciem")),
        Node("d2", "azure", app["resource_id"], "과도권한 App Registration",     app.get("pillar", "ciem")),
    ):
        graph.add_node(node)
    graph.add_edge(Edge("d1", "d2", "identity_takeover", False, "유출된 장기 SP 자격증명으로 과도권한 앱 장악 → Entra 디렉터리 전체 통제"))

    graph.apply_chain_severity()
    chain = [sp, app, consent]
    graph.finding_ids = [f["finding_id"] for f in chain if f and "finding_id" in f]
    return graph


# 발화 순서(빌더 목록) — correlate()가 전부 시도하고 발화한 것만 모은다.
_BUILDERS = (_build_hero, _build_aws_data_exfil, _build_azure_identity)


def _is_cross_cloud(graph: AttackPathGraph) -> bool:
    return any(e.cross_cloud for e in graph.edges)


def _rank_key(graph: AttackPathGraph):
    """위험도순 정렬 키(오름차순 = 위험한 것 먼저): severity 낮을수록(1=Critical) 먼저,
    같으면 크로스클라우드 우선, 그다음 노드 많은 순. hero(Critical·크로스클라우드·5노드)가 항상 최상단."""
    return (graph.severity_id, 0 if _is_cross_cloud(graph) else 1, -len(graph.nodes))


def _backfill_multi(findings: List[dict], ranked_graphs: List[AttackPathGraph]) -> None:
    """2-pass: 각 finding을 자신이 속한 **가장 위험도 높은 경로**에 귀속(attack_path_id 단일값).

    ranked_graphs는 이미 위험도순 → 앞 경로가 먼저 소유권을 가져간다(setdefault). 한 finding이
    여러 경로에 등장해도 최상위 경로 하나에만 태깅되고, 각 경로는 finding_ids로 전체 provenance를
    따로 보유한다(콘솔 경로 리스트는 attack_paths 테이블을 읽어 3경로 전부 렌더 — 태깅과 무관).
    """
    owner = {}  # type: dict
    for g in ranked_graphs:
        for fid in g.finding_ids:
            owner.setdefault(fid, g.attack_path_id)
    # 무조건 대입(set만 하지 않고 clear까지) — 어떤 경로에도 안 속한 finding은 None으로 비운다.
    # 조치로 경로가 사라진 뒤 재상관 시, RDS에서 로드된 stale attack_path_id(이미 삭제된 경로)를
    # 그대로 되쓰면 FK 위반(handler._backfill_findings)이 나므로 in-memory에서 미리 정리한다.
    for f in findings:
        f["attack_path_id"] = owner.get(f.get("finding_id"))


class CorrelationEngine:
    """R1~R5 규칙으로 finding 묶음 -> attack-path 그래프[] 생성(위험도순).

    실배포 스왑:
      - correlate()의 findings 파라미터를 RDS finding 조회 결과로 교체
      - _backfill_multi() 대신 RDS UPDATE attack_path_id 실행(handler.py)
    출력 구조는 계약③(attack-path.schema.json) 준수(그래프 조립·검증은 model/graph.py).
    """

    def correlate(self, findings: List[dict]) -> List[dict]:
        """findings 목록 -> attack_path 그래프 목록(계약③ JSON array, 위험도순).

        빌더 전부 시도 → 발화한 것만 수집 → 위험도순 정렬 → finding에 최상위 경로 backfill.
        """
        graphs = []  # type: List[AttackPathGraph]
        for build in _BUILDERS:
            g = build(findings)
            if not g:
                continue
            errs = validate_graph(g)  # 계약③ 불변식 검사(모델)
            if errs:
                raise ValueError("attack-path 그래프 불변식 위반: " + "; ".join(errs))
            graphs.append(g)

        graphs.sort(key=_rank_key)          # 위험도순(hero 최상단)
        _backfill_multi(findings, graphs)   # 각 finding을 최상위 소속 경로에 귀속
        return [g.to_dict() for g in graphs]  # finding_ids 제외한 계약③ 준수 dict[]
