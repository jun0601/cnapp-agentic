// audit·compliance 목업 데이터(콘솔-로컬, 계약 미졸업). 골든 시나리오 타임라인/컨트롤과 연결.
import type { AuditEvent, ComplianceReport } from '@/api/view-types'

// 감사로그 — HITL 조치·엔진 판정·스캔을 시간순(최신 위). 불변(S3 Object Lock) 가정.
export const AUDIT_EVENTS: AuditEvent[] = [
  { id: 'a12', ts: '2026-06-30T02:15:40Z', actor: 'jh_lee@demo', role: 'approver', action: 'approve', target: 'aws:s3_bucket:member-pii-prod', result: 'S3 Public Access Block 적용 → SFn 실행 시작' },
  { id: 'a11', ts: '2026-06-30T02:14:02Z', actor: 'jh_lee@demo', role: 'approver', action: 'view', target: 'case c0000000-…-0001', result: 'Evidence 4건·판정 confirmed 확인' },
  { id: 'a10', ts: '2026-06-30T02:12:30Z', actor: 'jw_kim@demo', role: 'viewer', action: 'reject', target: 'aws:security_group:sg-0product1234', result: '자동 SG 제거 보류 — 변경창구 협의 필요' },
  { id: 'a09', ts: '2026-06-30T02:05:11Z', actor: 'engine', role: 'system', action: 'verdict', target: 'case c0000000-…-0001', result: 'Reasoning confirmed (신뢰도 0.93) — 골든 경로 Critical 정당' },
  { id: 'a08', ts: '2026-06-30T02:03:18Z', actor: 'engine', role: 'system', action: 'verdict', target: 'aws:iam_role:order-irsa', result: 'Evidence: iam:SimulatePrincipalPolicy — 측면이동 경로 확인' },
  { id: 'a07', ts: '2026-06-30T02:03:10Z', actor: 'engine', role: 'system', action: 'verdict', target: 'aws:s3_bucket:member-pii-prod', result: 'Evidence: s3:GetBucketPolicy — 공개 버킷 확인' },
  { id: 'a06', ts: '2026-06-30T02:02:00Z', actor: 'engine', role: 'system', action: 'verdict', target: 'attack_path a0000000-…-0001', result: '트리아지 escalate=true (severity 1 AND attack_path)' },
  { id: 'a05', ts: '2026-06-30T02:00:30Z', actor: 'scanner:macie', role: 'system', action: 'scan', target: 'aws:s3_bucket:member-pii-prod', result: 'SensitiveData:PII 탐지 → f0000000-…-0007' },
  { id: 'a04', ts: '2026-06-30T02:00:12Z', actor: 'scanner:prowler', role: 'system', action: 'scan', target: 'shop/order', result: '평문 Azure SP 시크릿 탐지 → f0000000-…-0005' },
  { id: 'a03', ts: '2026-06-30T02:00:00Z', actor: 'scanner:securityhub', role: 'system', action: 'scan', target: 'batch scan_2026-06-30', result: 'findings 20건 수집 → cnapp.findings.batch.completed 발행' },
  { id: 'a02', ts: '2026-06-30T01:58:40Z', actor: 'jh_lee@demo', role: 'approver', action: 'login', target: 'console', result: 'Entra SSO 로그인 (custom:groups=approver)' },
  { id: 'a01', ts: '2026-06-30T01:50:00Z', actor: 'jw_kim@demo', role: 'viewer', action: 'login', target: 'console', result: 'Entra SSO 로그인 (custom:groups=viewer)' },
]

// 컴플라이언스 — ISMS-P 도메인 ↔ 우리 INTERNAL control 매핑(목업). 취약 타깃이라 fail 다수.
export const COMPLIANCE_REPORT: ComplianceReport = {
  framework: 'ISMS-P (요약 매핑)',
  generated_at: '2026-06-30T02:20:00Z',
  score: 0, // 아래 domains에서 계산해 채움
  domains: [
    {
      code: '2.5',
      name: '인증 및 권한관리',
      controls: [
        { code: '2.5.1', title: '사용자 MFA 적용', status: 'pass', findings: 0 },
        { code: '2.5.3', title: 'IAM/IRSA 최소권한', status: 'fail', mapped_control: 'INTERNAL-IAM-OVERPRIV-001', findings: 1 },
        { code: '2.5.6', title: 'Entra 앱 과도권한 금지', status: 'fail', mapped_control: 'INTERNAL-ENTRA-OVERPRIV-APP-001', findings: 1 },
      ],
    },
    {
      code: '2.6',
      name: '접근통제',
      controls: [
        { code: '2.6.1', title: '인터넷 노출 최소화(SG)', status: 'fail', mapped_control: 'INTERNAL-SG-OPEN-INGRESS-001', findings: 1 },
        { code: '2.6.4', title: 'S3 공개 접근 차단', status: 'fail', mapped_control: 'INTERNAL-S3-PUBLIC-001', findings: 1 },
      ],
    },
    {
      code: '2.7',
      name: '암호화',
      controls: [
        { code: '2.7.1', title: '저장 데이터 암호화(S3 KMS)', status: 'fail', mapped_control: 'INTERNAL-S3-NOENCRYPT-001', findings: 2 },
        { code: '2.7.3', title: '시크릿 평문 저장 금지', status: 'fail', mapped_control: 'INTERNAL-SECRET-PLAINTEXT-001', findings: 1 },
      ],
    },
    {
      code: '2.9',
      name: '로그 및 모니터링',
      controls: [
        { code: '2.9.1', title: 'CloudTrail 전 리전 수집', status: 'pass', findings: 0 },
        { code: '2.9.4', title: 'S3 접근로깅/버저닝', status: 'fail', mapped_control: 'INTERNAL-S3-LOGGING-DISABLED-001', findings: 1 },
      ],
    },
    {
      code: '2.11',
      name: '취약점 관리',
      controls: [
        { code: '2.11.1', title: '이미지 취약점(KEV) 차단', status: 'fail', mapped_control: 'INTERNAL-VULN-KEV-001', findings: 1 },
        { code: '2.11.2', title: 'ECR 스캔 활성화', status: 'fail', mapped_control: 'INTERNAL-ECR-SCAN-DISABLED-001', findings: 1 },
        { code: '2.11.5', title: '파드 권한 최소화(KSPM)', status: 'fail', mapped_control: 'INTERNAL-KSPM-PRIVILEGED-001', findings: 1 },
      ],
    },
    {
      code: '3.2',
      name: '개인정보 보호',
      controls: [
        { code: '3.2.2', title: '개인정보 공개노출 금지', status: 'fail', mapped_control: 'INTERNAL-DATA-PII-EXPOSED-001', findings: 1 },
      ],
    },
  ],
}

// score 계산(pass / (pass+fail), na 제외)
{
  const all = COMPLIANCE_REPORT.domains.flatMap((d) => d.controls)
  const pass = all.filter((c) => c.status === 'pass').length
  const fail = all.filter((c) => c.status === 'fail').length
  COMPLIANCE_REPORT.score = Math.round((pass / Math.max(1, pass + fail)) * 100)
}
