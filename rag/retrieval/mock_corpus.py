"""목업 RAG 코퍼스 (계약⑥ 구조, embedding 제외).

실배포: 준형이형(corpus/embedding 담당)이 Titan Embed v2로 벡터화해 pgvector에 적재.
목업: control_id → 청크 목록 직접 매핑 — pgvector 없이 end-to-end 흐름 검증용.

청크 구성 원칙:
  control 1개 = 청크 2~3개:
    [0] 위험 설명 (why dangerous)
    [1] 조치 방법 (how to fix)
    [2] 프레임워크 맥락 (선택)
"""
from __future__ import annotations

# control_id → [chunk dict] (계약⑥ — embedding 필드는 실배포 시 준형이형이 채움)
_CORPUS: dict[str, list[dict]] = {
    "INTERNAL-VULN-KEV-001": [
        {
            "chunk_id": "c1000000-0000-4000-8000-000000000001",
            "text": (
                "KEV(Known Exploited Vulnerabilities) 목록에 등재된 CVE는 "
                "CISA가 실제 공격에 활용됨을 확인한 취약점입니다. "
                "컨테이너 이미지 내 KEV CVE는 공격자가 이미 무기화한 익스플로잇으로 "
                "즉각적인 원격 코드 실행(RCE)이나 권한 상승으로 이어질 수 있어 "
                "Critical 등급으로 우선 처리해야 합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-VULN-KEV-001",
                "cloud": "aws",
                "service": "ECR/EKS",
                "framework": "KEV",
                "severity": 1,
                "lifecycle": "build",
                "remediable": True,
            },
        },
        {
            "chunk_id": "c1000000-0000-4000-8000-000000000002",
            "text": (
                "조치 방법: (1) 취약 이미지를 즉시 롤백하고 패치된 베이스 이미지로 "
                "재빌드합니다. (2) CI 파이프라인에 trivy --exit-code 1 게이트를 추가해 "
                "KEV CVE 포함 이미지의 ECR 푸시를 차단합니다. "
                "(3) Amazon Inspector를 활성화해 ECR scan-on-push를 켜두면 "
                "신규 이미지 푸시 시 자동 스캔됩니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-VULN-KEV-001",
                "cloud": "aws",
                "service": "ECR/EKS",
                "framework": "KEV",
                "severity": 1,
                "lifecycle": "build",
                "remediable": True,
            },
        },
    ],
    "INTERNAL-KSPM-PRIVILEGED-001": [
        {
            "chunk_id": "c1100000-0000-4000-8000-000000000001",
            "text": (
                "privileged: true 또는 hostPath 마운트가 설정된 파드는 "
                "컨테이너 격리를 우회해 호스트 노드의 파일시스템·프로세스에 "
                "직접 접근할 수 있습니다. "
                "CIS Kubernetes Benchmark 5.2 계열 위반이며, "
                "공격자가 컨테이너를 침해하면 EKS 노드 전체를 장악하는 "
                "권한 상승 경로가 됩니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-KSPM-PRIVILEGED-001",
                "cloud": "aws",
                "service": "EKS",
                "framework": "CIS",
                "severity": 2,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
        {
            "chunk_id": "c1100000-0000-4000-8000-000000000002",
            "text": (
                "조치: Pod Security Standards(PSS)의 restricted 프로파일을 "
                "네임스페이스에 적용합니다(kubectl label namespace shop "
                "pod-security.kubernetes.io/enforce=restricted). "
                "hostPath는 emptyDir 또는 PVC로 교체하고, "
                "privileged 컨테이너는 capabilities를 Drop ALL + 필요한 것만 Add로 변경합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-KSPM-PRIVILEGED-001",
                "cloud": "aws",
                "service": "EKS",
                "framework": "CIS",
                "severity": 2,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
    ],
    "INTERNAL-KSPM-CLUSTERADMIN-001": [
        {
            "chunk_id": "c1200000-0000-4000-8000-000000000001",
            "text": (
                "cluster-admin ClusterRole은 쿠버네티스에서 가장 강력한 권한(모든 "
                "리소스에 대한 모든 동작)을 부여합니다. 이 역할을 사람 계정·서비스 "
                "어카운트·그룹에 필요 이상으로 바인딩하면(CIS Kubernetes Benchmark "
                "5.1.1 계열 위반), 해당 주체가 침해될 경우 클러스터 전체가 즉시 "
                "장악됩니다. kubectl get clusterrolebindings로 cluster-admin "
                "바인딩 대상을 점검해야 합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-KSPM-CLUSTERADMIN-001",
                "cloud": "aws",
                "service": "EKS",
                "framework": "CIS",
                "severity": 2,
                "lifecycle": "runtime",
                "remediable": False,
            },
        },
        {
            "chunk_id": "c1200000-0000-4000-8000-000000000002",
            "text": (
                "조치: cluster-admin 바인딩을 꼭 필요한 관리자로만 좁히고, "
                "일반 워크로드·CI 서비스 어카운트에는 네임스페이스 범위의 최소 "
                "권한 Role을 별도로 정의해 RoleBinding으로 부여합니다(최소 권한 "
                "원칙). EKS에서는 aws-auth ConfigMap·access entry의 그룹 매핑도 "
                "함께 점검해 system:masters 남용이 없는지 확인합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-KSPM-CLUSTERADMIN-001",
                "cloud": "aws",
                "service": "EKS",
                "framework": "CIS",
                "severity": 2,
                "lifecycle": "runtime",
                "remediable": False,
            },
        },
    ],
    "INTERNAL-IAM-OVERPRIV-001": [
        {
            "chunk_id": "c4000000-0000-4000-8000-000000000001",
            "text": (
                "IRSA(IAM Roles for Service Accounts) 정책에 s3:* 와일드카드가 포함된 경우 "
                "파드가 침해되면 공격자는 모든 S3 버킷에 무제한 접근이 가능합니다. "
                "최소 권한 원칙(PoLP)에 따라 파드가 필요한 특정 버킷 ARN과 "
                "s3:GetObject·s3:PutObject 등 최소한의 액션만 허용해야 합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-IAM-OVERPRIV-001",
                "cloud": "aws",
                "service": "IAM/EKS",
                "framework": "CIS",
                "severity": 1,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
        {
            "chunk_id": "c4000000-0000-4000-8000-000000000002",
            "text": (
                "조치: IAM Role 인라인 정책의 Resource를 "
                "arn:aws:s3:::member-pii-prod/* 로 제한하고 "
                "Action을 s3:GetObject 등 실제 필요한 액션만으로 교체합니다. "
                "IAM Access Analyzer로 미사용 권한을 주기적으로 분석하고 "
                "IAM Access Advisor로 최근 90일 미사용 권한을 정리합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-IAM-OVERPRIV-001",
                "cloud": "aws",
                "service": "IAM/EKS",
                "framework": "CIS",
                "severity": 1,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
    ],
    "INTERNAL-SECRET-PLAINTEXT-001": [
        {
            "chunk_id": "c5000000-0000-4000-8000-000000000001",
            "text": (
                "Kubernetes Pod 환경변수나 매니페스트에 평문 자격증명이 노출된 경우 "
                "클러스터 접근 권한을 가진 모든 사용자 및 etcd 백업에서 "
                "해당 시크릿이 평문으로 확인됩니다. "
                "특히 Azure SP 자격증명이 노출되면 "
                "크로스클라우드 신원 탈취 경로가 열립니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-SECRET-PLAINTEXT-001",
                "cloud": "aws",
                "service": "EKS",
                "framework": "CIS",
                "severity": 1,
                "lifecycle": "build",
                "remediable": True,
            },
        },
        {
            "chunk_id": "c5000000-0000-4000-8000-000000000002",
            "text": (
                "조치: (1) 환경변수 직접 기재를 제거하고 AWS Secrets Manager + "
                "External Secrets Operator 또는 AWS Secrets Store CSI Driver로 교체합니다. "
                "(2) 노출된 Azure SP 자격증명은 즉시 rotate합니다. "
                "(3) git-secrets·Gitleaks를 CI에 추가해 평문 시크릿 커밋을 차단합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-SECRET-PLAINTEXT-001",
                "cloud": "aws",
                "service": "EKS",
                "framework": "CIS",
                "severity": 1,
                "lifecycle": "build",
                "remediable": True,
            },
        },
    ],
    "INTERNAL-S3-PUBLIC-001": [
        {
            "chunk_id": "c2000000-0000-4000-8000-000000000001",
            "text": (
                "S3 버킷 퍼블릭 액세스 허용은 AWS Security Hub S3.8 기준 위반입니다. "
                "Block Public Access 4개 플래그(BlockPublicAcls·IgnorePublicAcls·"
                "BlockPublicPolicy·RestrictPublicBuckets)가 모두 true여야 "
                "인터넷 직접 접근을 차단할 수 있습니다. "
                "PII가 포함된 버킷이 공개되면 개인정보보호법 위반으로 이어집니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-S3-PUBLIC-001",
                "cloud": "aws",
                "service": "S3",
                "framework": "FSBP",
                "severity": 1,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
        {
            "chunk_id": "c2000000-0000-4000-8000-000000000002",
            "text": (
                "조치: aws s3api put-public-access-block --bucket <버킷명> "
                "--public-access-block-configuration "
                "BlockPublicAcls=true,IgnorePublicAcls=true,"
                "BlockPublicPolicy=true,RestrictPublicBuckets=true. "
                "Terraform: aws_s3_bucket_public_access_block 리소스로 IaC 관리를 권장합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-S3-PUBLIC-001",
                "cloud": "aws",
                "service": "S3",
                "framework": "FSBP",
                "severity": 1,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
    ],
    "INTERNAL-S3-NOENCRYPT-001": [
        {
            "chunk_id": "c2100000-0000-4000-8000-000000000001",
            "text": (
                "S3 버킷에 서버 사이드 암호화(SSE-KMS)가 미설정된 경우 "
                "저장 데이터가 평문으로 보관됩니다. "
                "AWS Security Hub S3.4 기준이며, ISMS-P 2.7.1(암호화 적용) 요건에 해당합니다. "
                "고객 관리형 KMS 키(CMK)를 사용하면 키 교체·감사·접근 제어가 가능합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-S3-NOENCRYPT-001",
                "cloud": "aws",
                "service": "S3",
                "framework": "ISMS-P",
                "severity": 3,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
    ],
    "INTERNAL-S3-LOGGING-DISABLED-001": [
        {
            "chunk_id": "c2200000-0000-4000-8000-000000000001",
            "text": (
                "S3 버킷 접근 로깅 또는 버전 관리가 비활성화된 경우 "
                "데이터 유출·삭제 사고 발생 시 감사 추적이 불가능합니다. "
                "ISMS-P 2.9.4(접근 기록 관리) 요건이며, "
                "CloudTrail S3 데이터 이벤트와 함께 설정해 완전한 감사 로그를 확보합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-S3-LOGGING-DISABLED-001",
                "cloud": "aws",
                "service": "S3",
                "framework": "ISMS-P",
                "severity": 4,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
    ],
    "INTERNAL-DATA-PII-EXPOSED-001": [
        {
            "chunk_id": "c3000000-0000-4000-8000-000000000001",
            "text": (
                "Amazon Macie가 S3 버킷에서 민감 PII(주민등록번호·신용카드번호·"
                "여권번호 등)를 탐지한 경우, 해당 버킷이 퍼블릭이거나 "
                "과도한 권한으로 접근 가능하면 데이터 유출 위험이 Critical 수준입니다. "
                "ISMS-P 2.9.1(개인정보 처리) 및 개인정보보호법 제29조 위반에 해당합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-DATA-PII-EXPOSED-001",
                "cloud": "aws",
                "service": "S3/Macie",
                "framework": "ISMS-P",
                "severity": 1,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
        {
            "chunk_id": "c3000000-0000-4000-8000-000000000002",
            "text": (
                "조치: (1) Macie 분류 결과를 확인해 PII가 포함된 파일의 접근 제어를 강화합니다. "
                "(2) S3 Block Public Access 활성화 및 버킷 정책에서 불필요한 Principal 제거. "
                "(3) 개인정보처리방침에 따라 보존 기간 경과 데이터는 삭제 또는 익명화합니다. "
                "(4) CloudTrail + S3 데이터 이벤트로 접근 이력을 보관합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-DATA-PII-EXPOSED-001",
                "cloud": "aws",
                "service": "S3/Macie",
                "framework": "ISMS-P",
                "severity": 1,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
    ],
    "INTERNAL-SG-OPEN-INGRESS-001": [
        {
            "chunk_id": "c8000000-0000-4000-8000-000000000001",
            "text": (
                "보안 그룹 인바운드 규칙에 0.0.0.0/0(모든 IP)을 허용하면 "
                "인터넷에서 직접 접근이 가능합니다. "
                "EKS 워크로드의 경우 ALB→NodeGroup 방향만 허용하고, "
                "관리용 포트(22, 3389)는 특정 CIDR 또는 "
                "Systems Manager Session Manager로 대체해야 합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-SG-OPEN-INGRESS-001",
                "cloud": "aws",
                "service": "EC2/VPC",
                "framework": "FSBP",
                "severity": 2,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
        {
            "chunk_id": "c8000000-0000-4000-8000-000000000002",
            "text": (
                "조치: 보안 그룹 인바운드 규칙에서 0.0.0.0/0 항목을 삭제하고 "
                "ALB 보안 그룹 ID 참조(Source SG) 또는 사내 CIDR로 제한합니다. "
                "Terraform: aws_security_group_rule 리소스의 cidr_blocks에서 "
                "0.0.0.0/0 제거 후 source_security_group_id로 교체합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-SG-OPEN-INGRESS-001",
                "cloud": "aws",
                "service": "EC2/VPC",
                "framework": "FSBP",
                "severity": 2,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
    ],
    "INTERNAL-ENTRA-OVERPRIV-APP-001": [
        {
            "chunk_id": "c7000000-0000-4000-8000-000000000001",
            "text": (
                "Directory.ReadWrite.All 같은 광범위한 MS Graph 권한을 가진 "
                "App Registration이 침해되면 공격자는 Entra 테넌트 전체를 "
                "통제할 수 있습니다. 필요한 최소 Graph 권한(예: User.Read)만 "
                "부여하고, admin consent가 필요한 권한은 정기 검토 주기를 설정해야 합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-ENTRA-OVERPRIV-APP-001",
                "cloud": "azure",
                "service": "Entra ID",
                "framework": "CIS",
                "severity": 1,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
        {
            "chunk_id": "c7000000-0000-4000-8000-000000000002",
            "text": (
                "조치: Azure Portal → App Registrations → API Permissions에서 "
                "Directory.ReadWrite.All 권한을 제거하고 실제 필요한 최소 권한으로 교체합니다. "
                "Entra ID Privileged Identity Management(PIM)을 사용해 "
                "고권한은 Just-in-Time 방식으로만 부여합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-ENTRA-OVERPRIV-APP-001",
                "cloud": "azure",
                "service": "Entra ID",
                "framework": "CIS",
                "severity": 1,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
    ],
    "INTERNAL-ENTRA-SP-CRED-001": [
        {
            "chunk_id": "c6000000-0000-4000-8000-000000000001",
            "text": (
                "Azure Entra ID Service Principal 자격증명에 만료일이 없는 경우 "
                "유출 시 무기한 악용될 수 있습니다. "
                "Microsoft Identity 보안 권고에 따르면 SP 시크릿은 최대 1~2년 "
                "만료일을 설정하고, 가능하면 인증서 기반 인증이나 "
                "Federated Identity Credentials(키리스)로 대체해야 합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-ENTRA-SP-CRED-001",
                "cloud": "azure",
                "service": "Entra ID",
                "framework": "CIS",
                "severity": 2,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
        {
            "chunk_id": "c6000000-0000-4000-8000-000000000002",
            "text": (
                "조치: (1) az ad app credential reset --id <appId> "
                "--years 1 으로 만료일 1년짜리 새 시크릿 발급 후 기존 무만료 시크릿 삭제. "
                "(2) 장기적으로는 GitHub Actions → Federated Credential(OIDC)로 전환해 "
                "시크릿 자체를 없앱니다(키리스 인증). "
                "(3) Defender for Cloud CSPM 권고에서 지속 모니터링합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-ENTRA-SP-CRED-001",
                "cloud": "azure",
                "service": "Entra ID",
                "framework": "CIS",
                "severity": 2,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
    ],
    "INTERNAL-ENTRA-RISKY-CONSENT-001": [
        {
            "chunk_id": "c6100000-0000-4000-8000-000000000001",
            "text": (
                "검증되지 않은 앱에 대한 admin consent 허용은 "
                "공격자가 OAuth 피싱(consent phishing)으로 "
                "테넌트 데이터에 무단 접근하는 경로가 됩니다. "
                "Entra ID에서 사용자 consent 설정을 제한하고 "
                "admin consent 워크플로를 활성화해 검토 프로세스를 강제해야 합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-ENTRA-RISKY-CONSENT-001",
                "cloud": "azure",
                "service": "Entra ID",
                "framework": "CIS",
                "severity": 2,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
    ],
    "INTERNAL-ENTRA-INSECURE-CFG-001": [
        {
            "chunk_id": "c6200000-0000-4000-8000-000000000001",
            "text": (
                "App Registration의 리디렉션 URI에 와일드카드(*) 또는 "
                "localhost·http:// 주소가 포함된 경우 "
                "OAuth Authorization Code 흐름에서 토큰 탈취 공격에 노출됩니다. "
                "Microsoft Defender for Cloud secure score에서 "
                "앱 등록 보안 구성 항목으로 탐지됩니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-ENTRA-INSECURE-CFG-001",
                "cloud": "azure",
                "service": "Entra ID",
                "framework": "FSBP",
                "severity": 4,
                "lifecycle": "runtime",
                "remediable": True,
            },
        },
    ],
    "INTERNAL-ECR-SCAN-DISABLED-001": [
        {
            "chunk_id": "c9000000-0000-4000-8000-000000000001",
            "text": (
                "ECR 리포지토리의 scan-on-push가 비활성화된 경우 "
                "취약한 이미지가 ECR에 푸시되어도 자동으로 스캔되지 않습니다. "
                "AWS Security Hub ECR.1 기준이며, "
                "Amazon Inspector와 연동하면 OS·언어 패키지 모두 심층 스캔이 가능합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-ECR-SCAN-DISABLED-001",
                "cloud": "aws",
                "service": "ECR",
                "framework": "FSBP",
                "severity": 3,
                "lifecycle": "build",
                "remediable": True,
            },
        },
        {
            "chunk_id": "c9000000-0000-4000-8000-000000000002",
            "text": (
                "조치: aws ecr put-image-scanning-configuration "
                "--repository-name <repo> "
                "--image-scanning-configuration scanOnPush=true. "
                "Terraform: aws_ecr_repository의 image_scanning_configuration 블록에서 "
                "scan_on_push = true로 설정합니다."
            ),
            "metadata": {
                "control_id": "INTERNAL-ECR-SCAN-DISABLED-001",
                "cloud": "aws",
                "service": "ECR",
                "framework": "FSBP",
                "severity": 3,
                "lifecycle": "build",
                "remediable": True,
            },
        },
    ],
}


# 계약⑥ const 필드 — 실배포에서 준형이형이 pgvector 적재 시 동일 값 사용
# embedding_model·dim은 적재·검색 시 벡터 차원이 맞아야 하므로 계약으로 고정
_MOCK_CONST: dict = {
    "embedding_model": "amazon.titan-embed-text-v2:0",
    "dim": 1024,
    # embedding 필드(1024 floats)는 mock에서 의도적으로 제외:
    #   실배포 시 준형이형이 Titan Embed v2로 벡터화해 채움.
    #   목업은 control_id 직접 매핑으로 pgvector 없이 흐름 검증만 한다.
}


def _inject_const(chunk: dict) -> dict:
    """계약⑥ const 필드(embedding_model·dim)를 청크에 주입해 반환."""
    return {**chunk, **_MOCK_CONST}


def get_chunks_by_control(control_id: str) -> list[dict]:
    """control_id에 해당하는 청크 목록 반환 (계약⑥ const 필드 포함). 없으면 빈 리스트."""
    return [_inject_const(c) for c in _CORPUS.get(control_id, [])]


def all_chunks() -> list[dict]:
    """전체 청크 목록 (준형이형 corpus 적재 검증용, 계약⑥ const 필드 포함)."""
    result: list[dict] = []
    for chunks in _CORPUS.values():
        result.extend(_inject_const(c) for c in chunks)
    return result


def covered_controls() -> list[str]:
    """코퍼스가 커버하는 control_id 목록."""
    return list(_CORPUS.keys())
