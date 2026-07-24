"""정규화부 (진우 담당) — 스캐너 원본 → OCSF-lite finding 변환.

각 스캐너가 내놓는 포맷(ASFF·prowler-json·trivy-json)을 엔진·콘솔이
공통으로 쓰는 계약① finding.schema.json 형식으로 변환한다.

실배포 스왑: Lambda 핸들러가 SQS 메시지(계약⑤ ingest-envelope)에서
raw_inline/raw_location을 꺼내 Normalizer.normalize()로 넘기면 됨.
변환 로직(이 파일)은 무변.
"""
from __future__ import annotations

import fnmatch
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── control-catalog 로드 ──────────────────────────────────────────────
_CATALOG_PATH = Path(__file__).parent.parent.parent / "contracts" / "control-catalog.json"

def _load_catalog() -> dict:
    with open(_CATALOG_PATH, encoding="utf-8") as f:
        return json.load(f)

_CATALOG = _load_catalog()

# ── control-catalog 역인덱스 빌드 ─────────────────────────────────────
# source 표기: "securityhub:S3.8", "prowler:s3_bucket_public_access", "inspector:CVE-*"
# 정확 매칭과 와일드카드(*) 매칭을 모두 지원

def _build_source_index(catalog: dict) -> Tuple[Dict[str, str], List[Tuple[str, str]]]:
    exact: Dict[str, str] = {}      # "securityhub:S3.8" → "INTERNAL-S3-PUBLIC-001"
    wildcards: List[Tuple[str, str]] = []  # [("inspector:CVE-*", "INTERNAL-VULN-KEV-001"), ...]
    for ctrl_id, meta in catalog.get("controls", {}).items():
        for src in meta.get("sources", []):
            if "*" in src:
                wildcards.append((src, ctrl_id))
            else:
                exact[src] = ctrl_id
    return exact, wildcards

_EXACT_INDEX, _WILDCARD_INDEX = _build_source_index(_CATALOG)


def lookup_control(source_key: str) -> Optional[str]:
    """source:checkId → INTERNAL control_id. 없으면 None."""
    if source_key in _EXACT_INDEX:
        return _EXACT_INDEX[source_key]
    for pattern, ctrl_id in _WILDCARD_INDEX:
        if fnmatch.fnmatch(source_key, pattern):
            return ctrl_id
    return None


# ── severity 변환 ─────────────────────────────────────────────────────
# 내부 컨벤션: 1=Critical ~ 5=Info (낮을수록 심각 — OCSF와 반대, finding.schema.json 주석 참고)
_ASFF_SEV = {"CRITICAL": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4, "INFORMATIONAL": 5}
_PROWLER_SEV = {"critical": 1, "high": 2, "medium": 3, "low": 4, "informational": 5}

def _asff_severity(label: str) -> int:
    return _ASFF_SEV.get(label.upper(), 3)

def _prowler_severity(label: str) -> int:
    return _PROWLER_SEV.get(label.lower(), 3)

# OCSF severity_id(0 Unknown·1 Info·2 Low·3 Medium·4 High·5 Critical·6 Fatal)
# → 내부 컨벤션(1 Critical ~ 5 Info). 방향이 반대라 매핑 필요.
_OCSF_SEV = {0: 3, 1: 5, 2: 4, 3: 3, 4: 2, 5: 1, 6: 1}

def _ocsf_severity_id(sid) -> int:
    try:
        return _OCSF_SEV.get(int(sid), 3)
    except (TypeError, ValueError):
        return 3


# ── resource_id 캐논화 (4.4.1a 규칙) ─────────────────────────────────
# 형식: {cloud}:{type}:{native_id}
# ARN이면 마지막 경로 세그먼트만 취함. 계정ID·리전 제외.
_ASFF_RTYPE = {
    "AwsS3Bucket":         "s3_bucket",
    "AwsIamRole":          "iam_role",
    "AwsEc2SecurityGroup": "security_group",
    "AwsEcrRepository":    "ecr_repo",
    "AwsEksCluster":       "eks_pod",     # 클러스터 수준 finding
}
_PROWLER_RTYPE = {
    "s3":            "s3_bucket",
    "iam":           "iam_role",
    "ec2":           "security_group",
    "ecr":           "ecr_repo",
    "eks":           "eks_pod",
    "secretsmanager":"secret_plaintext",
    "entraid":       "service_principal",  # Prowler Azure
    "entra_id":      "service_principal",
    "appregistration": "app_registration",
}
_ACCESS_ANALYZER_RTYPE = {
    "AWS::S3::Bucket":       "s3_bucket",
    "AWS::IAM::Role":        "iam_role",
    "AWS::ECR::Repository":  "ecr_repo",
}

def _arn_to_native(arn: str) -> str:
    """ARN → native_id: 마지막 세그먼트(/ 또는 : 구분). S3는 버킷명만."""
    if not arn.startswith("arn:"):
        return arn  # 이미 native ID이면 그대로
    parts = arn.split(":")
    # S3: arn:aws:s3:::bucket-name → parts[-1] = bucket-name
    native = parts[-1]
    # 경로 포함(IAM role 등): arn:aws:iam::acct:role/my-role → "role/my-role" → "my-role"
    if "/" in native:
        native = native.split("/")[-1]
    return native

def _canon_resource_id(cloud: str, rtype: str, raw_id: str) -> str:
    """cloud:rtype:native_id 형태로 정규화. 이미 캐논 형식이면 그대로."""
    # 이미 캐논 형식(cloud:type:native_id)이면 재가공 금지
    if raw_id.startswith(("aws:", "azure:")):
        return raw_id
    native = _arn_to_native(raw_id)
    return f"{cloud}:{rtype}:{native}"


# ── ASFF 파서 (Security Hub · Inspector · Macie) ─────────────────────
# 2026-07-24 실측: Inspector가 relay한 ASFF는 Security Hub 자체 체크(S3.2 등)와 달리
# `ProductFields`·`Compliance`가 키 자체는 있는데 값이 명시적 null이다(누락이 아니라 null).
# `raw.get("X", {})`는 키가 있고 값이 None이면 기본값을 안 쓰고 None을 그대로 돌려줘서
# 그 다음 `.get(...)` 호출이 AttributeError로 죽는다 — Inspector finding이 하나라도 배치에
# 섞이면 normalize 전체가 크래시했던 실제 원인(273건이 Security Hub까지는 왔는데 콘솔에
# 하나도 안 보이던 것). `or {}`로 None-safety 확보.
def _parse_asff(raw: dict, source: str, cloud_hint: str) -> List[dict]:
    """ASFF 단건 → finding 목록(보통 1건, 복수 리소스면 복수)."""
    findings = []
    resources = raw.get("Resources") or [{}]
    sev_label = (raw.get("Severity") or {}).get("Label", "MEDIUM")
    title = raw.get("Title", "")
    updated_at = raw.get("UpdatedAt", _now())
    created_at = raw.get("CreatedAt", updated_at)

    compliance_status = (raw.get("Compliance") or {}).get("Status")
    if compliance_status == "FAILED":
        status = "open"
    elif compliance_status == "PASSED":
        status = "remediated"
    else:
        # Compliance 개념 자체가 없는 제품(Inspector의 CVE·네트워크 도달성 등) — "합격/불합격"이
        # 아니라 "탐지됐다" 자체가 문제이므로, 기본값을 remediated로 두면 실 취약점이 조용히
        # 안 보이게 된다. 탐지된 이상 open으로 취급.
        status = "open"

    # control key: "securityhub:S3.8" 형태로 lookup
    ctrl_key = (raw.get("ProductFields") or {}).get("ControlId", "")
    if ctrl_key:
        ctrl_key = f"{source}:{ctrl_key}"
    # GeneratorId fallback: "security-control/S3.8" → "S3.8"
    if not ctrl_key:
        gen = raw.get("GeneratorId", "")
        if "security-control/" in gen:
            ctrl_key = f"securityhub:{gen.split('security-control/')[-1]}"

    # Macie: Types 기반(ASFF 경유 — 실측상 POLICY 카테고리만 여기로 옴, 2026-07-24).
    # 와일드카드는 실제 Macie type 포맷("SensitiveData:S3Object/...", 콜론)과 맞춰야 함
    # — 예전엔 "/"였는데 이러면 절대 안 매칭됐다(_parse_macie 신설 계기로 같이 발견·수정).
    types = raw.get("Types") or []
    if any("SensitiveData" in t for t in types):
        ctrl_key = "macie:SensitiveData:*"  # wildcard match용

    # Inspector: GeneratorId가 그냥 "AWSInspector"라 체크별 구분이 안 되지만, CVE finding은
    # Title이 항상 "CVE-XXXX-YYYYY - ..." 형식이라 여기서 CVE ID를 뽑아 카탈로그의
    # 기존 "inspector:CVE-*" 와일드카드(트리비와 대칭으로 처음부터 있었음)에 매핑한다.
    # source 파라미터는 항상 "securityhub"(relay 경유)지만, CVE 패턴은 Inspector 고유
    # 신호라 실제 탐지 주체를 정확히 라벨링할 수 있는 드문 경우.
    if not ctrl_key and title.startswith("CVE-"):
        cve_id = title.split(" ", 1)[0]
        ctrl_key = f"inspector:{cve_id}"

    control_id = lookup_control(ctrl_key) if ctrl_key else None

    for res in resources:
        rtype_asff = res.get("Type", "")
        rtype = _ASFF_RTYPE.get(rtype_asff, "other")
        raw_id = res.get("Id", "")
        rid = _canon_resource_id(cloud_hint, rtype, raw_id)
        dedup = f"{rid}|{control_id}" if control_id else f"{rid}|unknown"

        findings.append(_make_finding(
            cloud=cloud_hint,
            resource_id=rid,
            resource_type=rtype,
            control_id=control_id or "INTERNAL-UNKNOWN-001",
            title=title,
            severity_id=_asff_severity(sev_label),
            status=status,
            source_key=ctrl_key or source,
            dedup_key=dedup,
            first_seen=created_at,
            last_seen=updated_at,
        ))
    return findings


# ── Prowler JSON 파서 (AWS + Azure) ──────────────────────────────────
def _parse_prowler(raw: dict, cloud_hint: str) -> List[dict]:
    """Prowler JSON 단건 → finding 1건."""
    check_id = raw.get("checkID", raw.get("check_id", ""))
    source_key = f"prowler:{check_id}"
    control_id = lookup_control(source_key)

    service = raw.get("service", check_id.split("_")[0] if check_id else "other")
    rtype = _PROWLER_RTYPE.get(service.lower(), "other")

    # resource ID: resourceArn 있으면 ARN→native, 없으면 resourceId 직접
    raw_id = raw.get("resourceArn") or raw.get("resource_arn") or raw.get("resourceId") or raw.get("resource_id", "")
    cloud = raw.get("cloud", cloud_hint)
    rid = _canon_resource_id(cloud, rtype, raw_id)

    status_raw = raw.get("status", raw.get("Status", "FAIL")).upper()
    # 노이즈 억제(2026-07-08 실측: 계정 전체 Prowler 스캔이 처음 관통하며 매핑 안 된 PASS
    # 체크 1023건이 전부 INTERNAL-UNKNOWN-001로 쌓임) — kube-bench 파서(_parse_kube_bench)와
    # 동일 규칙: 카탈로그에 매핑 안 되는 체크는 FAIL일 때만 finding을 만든다.
    if control_id is None and status_raw != "FAIL":
        return []
    status = "open" if status_raw == "FAIL" else "remediated"

    sev = raw.get("severity", raw.get("Severity", "medium"))
    ts = raw.get("timestamp", raw.get("Timestamp", _now()))
    dedup = f"{rid}|{control_id}" if control_id else f"{rid}|{source_key}"

    return [_make_finding(
        cloud=cloud,
        resource_id=rid,
        resource_type=rtype,
        control_id=control_id or "INTERNAL-UNKNOWN-001",
        title=raw.get("checkTitle", raw.get("check_title", check_id)),
        severity_id=_prowler_severity(sev),
        status=status,
        source_key=source_key,
        dedup_key=dedup,
        first_seen=ts,
        last_seen=ts,
    )]


# ── OCSF 파서 (Prowler `-M json-ocsf` — AWS+Azure 공통) ───────────────
# 설계 확정(project-draft §24·계약⑤): 실 Prowler는 OCSF로 출력 → S3 → ingest가
# source_format="ocsf"로 봉투화(from_s3_event). OCSF는 클라우드 중립이라 AWS 전용
# ASFF와 달리 Azure Entra까지 파서 하나로 커버한다("멀티클라우드 OCSF 통합" 셀링포인트).
# ⚠️ OCSF는 Prowler 버전별로 필드 위치가 조금씩 달라 여러 경로를 방어적으로 탐색한다.
#    (실 OCSF fixture 확보 전이라 run_demo의 mock OCSF로 shape 검증 — 실전환 시 실출력과 대조)
def _parse_ocsf(raw: dict, cloud_hint: str) -> List[dict]:
    """OCSF Detection Finding(Prowler) 단건 → finding 목록(resources[]별 1건)."""
    unmapped = raw.get("unmapped") or {}
    # check_id: control 매핑 키. Prowler OCSF는 metadata.event_code에 체크ID를 둔다.
    check_id = (
        raw.get("metadata", {}).get("event_code")
        or unmapped.get("check_id")
        or unmapped.get("CheckID")
        or ""
    )
    source_key = f"prowler:{check_id}" if check_id else "prowler:unknown"
    control_id = lookup_control(source_key)

    cloud = (raw.get("cloud") or {}).get("provider") or cloud_hint

    # status: OCSF status_code(PASS/FAIL) 우선 → FAIL=open. status("New"/"Suppressed") 보조.
    status_code = str(raw.get("status_code") or raw.get("status") or "FAIL").upper()
    status = "open" if status_code in ("FAIL", "FAILED", "NEW") else "remediated"
    # 노이즈 억제(2026-07-08, _parse_prowler·kube-bench 파서와 동일 규칙): 카탈로그에
    # 매핑 안 되는 체크는 open(FAIL)일 때만 finding을 만든다.
    if control_id is None and status != "open":
        return []

    # severity: Prowler가 문자열("High" 등) 주면 그걸 우선(ASFF/prowler와 동일 매핑),
    # 없으면 OCSF 숫자 severity_id를 내부 컨벤션으로 뒤집어 매핑.
    sev_label = raw.get("severity")
    severity_id = _prowler_severity(sev_label) if sev_label else _ocsf_severity_id(raw.get("severity_id", 3))

    title = raw.get("finding_info", {}).get("title") or raw.get("message") or check_id
    ts = raw.get("time_dt") or raw.get("time")
    if not isinstance(ts, str):
        ts = _now()

    findings: List[dict] = []
    for res in (raw.get("resources") or [{}]):
        raw_id = res.get("uid") or res.get("name") or ""
        # 리소스 타입: OCSF resources[].group.name(=Prowler service) → _PROWLER_RTYPE.
        # 없으면 type 문자열로 폴백. Azure는 resourceId가 이미 캐논(azure:...)이면 passthrough.
        svc = (res.get("group") or {}).get("name") or res.get("type") or ""
        rtype = _PROWLER_RTYPE.get(str(svc).lower(), "other")
        rid = _canon_resource_id(cloud, rtype, raw_id)
        dedup = f"{rid}|{control_id}" if control_id else f"{rid}|{source_key}"
        findings.append(_make_finding(
            cloud=cloud,
            resource_id=rid,
            resource_type=rtype,
            control_id=control_id or "INTERNAL-UNKNOWN-001",
            title=title,
            severity_id=severity_id,
            status=status,
            source_key=source_key,
            dedup_key=dedup,
            first_seen=ts,
            last_seen=ts,
        ))
    return findings


# ── Trivy JSON 파서 ───────────────────────────────────────────────────
def _parse_trivy(raw: dict, cloud_hint: str) -> List[dict]:
    """Trivy JSON(이미지 스캔) → finding 목록. CVE별 1건."""
    artifact = raw.get("ArtifactName", "unknown")
    # 이미지 태그 제거: "shop/product:latest" → "shop/product"
    # 태그는 마지막 ":"이후 "/" 없는 세그먼트. ECR URL의 ":"(포트 없음)와 구분.
    if ":" in artifact:
        name, maybe_tag = artifact.rsplit(":", 1)
        if "/" not in maybe_tag:
            artifact = name
    results = raw.get("Results", [])
    findings = []
    for result in results:
        for vuln in result.get("Vulnerabilities", []):
            cve = vuln.get("VulnerabilityID", "")
            sev = vuln.get("Severity", "MEDIUM")
            source_key = f"trivy:{cve}"
            control_id = lookup_control(source_key) or "INTERNAL-VULN-KEV-001"
            rid = f"aws:eks_pod:{artifact}"
            # 계약①: dedup_key = resource_id|control_id(2세그먼트) — 이미지에 CVE가 여러 개
            # 있어도 같은 control(대부분 INTERNAL-VULN-KEV-001 하나뿐, control-catalog.json
            # "trivy:CVE-*" 와일드카드)이면 finding 1건으로 합쳐지고 각 CVE는 sources에
            # 누적된다(dedup_findings). 2026-07-03 재검증: 이전엔 |{cve} 3세그먼트를 써서
            # CVE마다 별도 finding이 생겨 계약①·골든 mock-findings.json의 "이미지당 1건"
            # 의도와 어긋났었음(준형 판단: 계약이 2세그먼트로 정의하므로 normalizer가 계약
            # 위반이었음) — 2세그먼트로 수정.
            dedup = f"{rid}|{control_id}"
            findings.append(_make_finding(
                cloud=cloud_hint,
                resource_id=rid,
                resource_type="eks_pod",
                control_id=control_id,
                title=f"KEV-listed CVE ({cve}) in {artifact} image",
                severity_id=_asff_severity(sev),
                status="open",
                source_key=source_key,
                dedup_key=dedup,
                first_seen=_now(),
                last_seen=_now(),
            ))
    return findings


# ── kube-bench 파서 (KSPM, custom 포맷) ────────────────────────────────
# kube-bench는 노드/클러스터 스코프 도구라 원생 출력엔 파드 귀속 정보가 없다
# — 스캐너(scanners/workload/kube_bench.py KubeBenchScanner._build_envelope)가
# raw_inline에 얹어준 target_resource로 resource_id를 만든다(모델링 단순화,
# 그 파일 모듈 docstring 참고). kube-bench는 severity를 안 내놓음(CIS
# 벤치마크는 pass/fail + scored만) — control-catalog의 severity_default를 쓴다.
def _parse_kube_bench(raw: dict, cloud_hint: str) -> List[dict]:
    """kube-bench CIS 벤치마크 JSON(Controls[].controls.tests[].results[]) → finding 목록."""
    target = raw.get("target_resource", "unknown")
    rid = f"aws:eks_pod:{target}"
    ts = raw.get("timestamp") or _now()

    findings: List[dict] = []
    for group in raw.get("Controls", []):
        controls = group.get("controls", group)
        for test in controls.get("tests", []):
            for result in test.get("results", []):
                test_number = result.get("test_number", "")
                source_key = f"kube-bench:{test_number}"
                control_id = lookup_control(source_key)

                status_raw = str(result.get("status", "FAIL")).upper()
                # 노이즈 억제(2026-07-06): 카탈로그에 매핑 안 되는(control=None) 체크는
                #   실패(FAIL)일 때만 INTERNAL-UNKNOWN-001로 올린다. PASS/WARN/INFO는
                #   "통과한 미매핑 벤치마크" = 정보성 잡음이라 finding으로 만들지 않음
                #   (실 클러스터 스캔은 수십~수백 PASS를 쏟아내는데 전부 UNKNOWN-remediated로
                #    쌓이면 콘솔이 지저분해짐 — 매핑된 control은 PASS도 remediated로 유지).
                if control_id is None and status_raw != "FAIL":
                    continue
                if control_id is None:
                    control_id = "INTERNAL-UNKNOWN-001"
                catalog_meta = _CATALOG.get("controls", {}).get(control_id, {})
                severity_id = catalog_meta.get("severity_default", 3)

                status = "open" if status_raw == "FAIL" else "remediated"
                dedup = f"{rid}|{control_id}"

                findings.append(_make_finding(
                    cloud=cloud_hint,
                    resource_id=rid,
                    resource_type="eks_pod",
                    control_id=control_id,
                    title=f"{result.get('test_desc', test_number)} ({target})",
                    severity_id=severity_id,
                    status=status,
                    source_key=source_key,
                    dedup_key=dedup,
                    first_seen=ts,
                    last_seen=ts,
                ))
    return findings


# ── IAM Access Analyzer 파서 (CIEM, custom 포맷) ───────────────────────
# boto3 accessanalyzer.list_findings() Findings[] 원소를 직접 받는다(Prowler 경유 아님 —
# AWS 네이티브 정책 도달성 분석 엔진, scanners/ciem/aws_access_analyzer.py). 이미 계약
# control-catalog.json의 INTERNAL-IAM-OVERPRIV-001.sources에 "access-analyzer:*" 와일드카드가
# 예비 등록돼 있었음 — 이 파서가 그 자리를 채운다(신규 control 안 만듦, 기존 설계 의도 재사용).
# ⚠️ 2026-07-22: boto3 클라이언트명(accessanalyzer, 하이픈 없음)이 아니라 실 AWS 서비스 표기
# (access-analyzer, 하이픈 있음)로 통일 — IAM 정책과는 무관한 내부 라벨이지만 화면에 노출되는 값.
def _parse_access_analyzer(raw: dict, cloud_hint: str) -> List[dict]:
    """Access Analyzer finding(단건) → finding 1건. severity는 카탈로그가 안 주는 신호라
    isPublic으로 산출(퍼블릭=Critical, 특정 계정/주체로 스코프된 외부접근=High)."""
    rtype_aa = raw.get("resourceType", "")
    source_key = f"access-analyzer:{rtype_aa}"
    control_id = lookup_control(source_key) or "INTERNAL-UNKNOWN-001"

    rtype = _ACCESS_ANALYZER_RTYPE.get(rtype_aa, "other")
    raw_id = raw.get("resource", "")
    rid = _canon_resource_id(cloud_hint, rtype, raw_id)

    status_raw = str(raw.get("status", "ACTIVE")).upper()
    status = "open" if status_raw == "ACTIVE" else "remediated"

    severity_id = 1 if raw.get("isPublic") else 2
    scope = "공개(Public)" if raw.get("isPublic") else "특정 외부 계정/주체"
    title = f"IAM Access Analyzer: {rtype_aa} externally reachable ({scope})"

    ts = raw.get("createdAt") or raw.get("analyzedAt") or _now()
    if not isinstance(ts, str):
        ts = _now()
    updated = raw.get("updatedAt") or raw.get("analyzedAt") or ts
    if not isinstance(updated, str):
        updated = ts

    dedup = f"{rid}|{control_id}"
    return [_make_finding(
        cloud=cloud_hint,
        resource_id=rid,
        resource_type=rtype,
        control_id=control_id,
        title=title,
        severity_id=severity_id,
        status=status,
        source_key=source_key,
        dedup_key=dedup,
        first_seen=ts,
        last_seen=updated,
    )]


# ── Macie 파서 (DSPM, custom 포맷) ─────────────────────────────────────
# 2026-07-24 실측: Macie finding은 category별로 Security Hub relay 여부가 다르다 —
# POLICY 카테고리(버킷 설정류)는 자동으로 ASFF로 relay되지만, CLASSIFICATION 카테고리
# (SensitiveData — 우리가 쓰는 PII 탐지)는 Security Hub로 전혀 안 온다(AWS 설계상 구분,
# 버그 아님). 그래서 scan_securityhub() 경유가 아니라 scanners/cspm/cspm.py의
# scan_macie()가 macie2.get_findings() 원본을 직접 custom 포맷으로 봉투화해 여기로 온다.
def _parse_macie(raw: dict, cloud_hint: str) -> List[dict]:
    """Macie SensitiveData finding(macie2.get_findings 원소, 단건) → finding 1건."""
    ftype = raw.get("type", "SensitiveData")
    source_key = f"macie:{ftype}"
    control_id = lookup_control(source_key) or "INTERNAL-UNKNOWN-001"

    bucket = ((raw.get("resourcesAffected") or {}).get("s3Bucket") or {}).get("name", "")
    rid = _canon_resource_id(cloud_hint, "s3_bucket", bucket) if bucket else f"{cloud_hint}:s3_bucket:unknown"

    sev_label = ((raw.get("severity") or {}).get("description")) or "MEDIUM"
    severity_id = _asff_severity(sev_label)

    ts = raw.get("createdAt") or _now()
    if not isinstance(ts, str):
        ts = _now()
    updated = raw.get("updatedAt") or ts
    if not isinstance(updated, str):
        updated = ts

    # 실제 발견 건수는 최상위 count(=이 finding 레코드 개수, 항상 1)가 아니라
    # classificationDetails.result 안의 customDataIdentifiers/sensitiveData 집계에 있다
    # (2026-07-24 실측: top-level count=1인데 커스텀 식별자 totalCount=200이었음 — 처음엔
    # count를 그대로 써서 "(1건)"으로 잘못 표시했다가 발견·수정).
    result = ((raw.get("classificationDetails") or {}).get("result")) or {}
    cdi_total = (result.get("customDataIdentifiers") or {}).get("totalCount", 0)
    sens_total = sum(item.get("totalCount", 0) for item in (result.get("sensitiveData") or []))
    count = cdi_total + sens_total or raw.get("count", 1)
    title = f"{ftype} detected in {bucket} ({count}건)" if bucket else ftype

    dedup = f"{rid}|{control_id}"
    return [_make_finding(
        cloud=cloud_hint,
        resource_id=rid,
        resource_type="s3_bucket",
        control_id=control_id,
        title=title,
        severity_id=severity_id,
        status="open",
        source_key=source_key,
        dedup_key=dedup,
        first_seen=ts,
        last_seen=updated,
    )]


# ── finding 조립 헬퍼 ─────────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _make_finding(
    cloud: str,
    resource_id: str,
    resource_type: str,
    control_id: str,
    title: str,
    severity_id: int,
    status: str,
    source_key: str,
    dedup_key: str,
    first_seen: str,
    last_seen: str,
) -> dict:
    """계약① finding 조립. finding_id는 UUID v4 신규 발급."""
    if resource_type not in (
        "s3_bucket","iam_role","eks_pod","security_group",
        "secret_plaintext","app_registration","service_principal","ecr_repo",
    ):
        resource_type = "other"

    # ── 미매핑 finding은 open이 아니라 suppressed로 내린다(2026-07-23) ──────────
    # 카탈로그에 없는 체크는 "우리 제품이 해석할 수 없는 신호"이지 "우리가 관리하는 위험"이
    # 아니다. open으로 두면 실측 두 가지가 망가진다:
    #   ① Secure Score 붕괴 — 점수는 open findings 심각도 가중으로 산출(console-backend
    #      getScores)이라, 실계정 Prowler cron이 매일 쏟는 일반 posture 체크 314건이
    #      점수를 10/100까지 끌어내렸다(깨끗할 땐 AWS 35·Azure 79).
    #   ② 비용 게이트가 뚫림 — 그 314건 중 Critical 11·High 77 = 88건이 트리아지 게이트
    #      (severity_id<=2)를 통과해 Bedrock 조사를 유발한다. 비용을 막으라고 만든 게이트가
    #      정작 노이즈에 열려 있었다(engine/evidence/triage.py).
    # 지금까지는 발견할 때마다 psql로 DELETE했으나(2026-07-08·07-22 두 번) cron이 매일
    # 재생성해서 근본 해결이 아니었다. suppressed는 삭제와 다르다 — 데이터는 남아서 총
    # findings 수 = 실제 수집량 그대로이고(스캐너가 무엇을 봤는지 감사 가능), open 집계와
    # 트리아지 게이트(status=="open" 조건)에서만 빠진다. 나중에 control-catalog에 매핑을
    # 추가하면 다음 스캔부터 저절로 open으로 올라온다.
    if control_id == "INTERNAL-UNKNOWN-001" and status == "open":
        status = "suppressed"

    catalog_meta = _CATALOG.get("controls", {}).get(control_id, {})
    pillar = catalog_meta.get("pillar", "cspm")
    return {
        "finding_id": str(uuid.uuid4()),
        "cloud": cloud,
        "resource_id": resource_id,
        "resource_type": resource_type,
        "pillar": pillar,
        "control_id": control_id,
        "title": title,
        "severity_id": severity_id,
        "status": status,
        "sources": [source_key],
        "dedup_key": dedup_key,
        "priority_score": None,
        "attack_path_id": None,
        "ai_status": "pending",
        "first_seen": first_seen,
        "last_seen": last_seen,
        "raw_ref": None,
    }


# ── dedup: 같은 dedup_key면 source 누적, finding은 1개 ────────────────
def dedup_findings(findings: List[dict]) -> List[dict]:
    """dedup_key 기준 중복 제거. sources는 union, last_seen은 최신으로."""
    seen: Dict[str, dict] = {}
    for f in findings:
        key = f["dedup_key"]
        if key not in seen:
            seen[key] = f
        else:
            existing = seen[key]
            # sources 누적(중복 제거)
            existing["sources"] = list(set(existing["sources"]) | set(f["sources"]))
            # last_seen 최신 유지
            if f["last_seen"] > existing["last_seen"]:
                existing["last_seen"] = f["last_seen"]
    return list(seen.values())


# ── 메인 Normalizer ───────────────────────────────────────────────────
class Normalizer:
    """ingest-envelope → 계약① finding[] 변환기.

    실배포: Lambda 핸들러에서 Normalizer().normalize(envelope) 호출.
    목업:   run_demo.py가 mock envelope으로 직접 호출.
    """

    def normalize(self, envelope: dict) -> List[dict]:
        """계약⑤ ingest-envelope → 계약① finding 목록(dedup 완료)."""
        source = envelope.get("source", "")
        source_format = envelope.get("source_format", "")
        cloud_hint = envelope.get("cloud_hint", "aws")
        raw = envelope.get("raw_inline") or {}

        # raw_inline이 배열이면 각각 처리(Prowler 배치 등)
        raw_list = raw if isinstance(raw, list) else [raw]

        findings: List[dict] = []
        for item in raw_list:
            if not item:
                continue
            parsed = self._parse_one(item, source, source_format, cloud_hint)
            findings.extend(parsed)

        return dedup_findings(findings)

    def _parse_one(self, raw: dict, source: str, fmt: str, cloud_hint: str) -> List[dict]:
        if fmt == "asff":
            # Security Hub / Inspector / Macie 공통
            return _parse_asff(raw, source, cloud_hint)
        if fmt == "prowler-json":
            return _parse_prowler(raw, cloud_hint)
        if fmt == "ocsf":
            # Prowler json-ocsf(실 Azure·AWS 경로) — from_s3_event가 이 포맷으로 봉투화
            return _parse_ocsf(raw, cloud_hint)
        if fmt == "trivy-json":
            return _parse_trivy(raw, cloud_hint)
        if fmt == "custom":
            if source == "kube-bench":
                return _parse_kube_bench(raw, cloud_hint)
            if source == "access-analyzer":
                return _parse_access_analyzer(raw, cloud_hint)
            if source == "macie":
                return _parse_macie(raw, cloud_hint)
            # 그 외 custom(manifest scan 등)은 이미 정규화된 finding dict로 간주
            if "finding_id" in raw:
                return [raw]
        return []
