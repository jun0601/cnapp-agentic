# 인프라/계정 현황 (Status Log)

> 설계 문서([project-draft.md](project-draft.md) 등)는 **"무엇을 만들지" 결정**을 담고, 이 문서는 **"지금 실제로 무엇이 설정·구축돼 있는지" 현황**을 기록한다.
> 설계가 바뀌면 먼저 설계 문서를 갱신하고, 이 문서는 실제로 콘솔/Terraform으로 실행한 뒤에 갱신한다. CLAUDE.md는 이 문서를 가리키는 포인터만 둔다.

---

## AWS 계정 초기 설정 ✅

> 새 무료 플랜 AWS 계정 기준으로 완료된 설정. project-draft.md D1~D3(11번) 가드레일 그대로 반영. 협업자도 이 상태를 전제로 작업 시작.

| 영역 | 설정 내용 |
|---|---|
| **계정 기본** | 단일 계정, 콘솔 기본 리전 **서울(ap-northeast-2)**. 계정 별칭 설정 완료. Organizations/Identity Center/Control Tower **미활성 확인됨**. |
| **루트 계정** | MFA(가상 MFA 앱) 활성화. 액세스 키 없음(보유 시 즉시 삭제 원칙). 이후 평상시 로그인 안 함 — 비상용(결제 변경 등)으로만 보관. |
| **결제 가드레일** | Billing → "계정(Account)" 페이지에서 **IAM 사용자/역할의 결제 정보 액세스 활성화** 완료. Free Tier 사용량 알림 ON. AWS Budgets **$50 / $100** 2단계 알림 생성(임계값 80%/100%, 본인+협업자 이메일 수신). |
| **IAM 사용자** | Identity Center 미사용 → **개인별 IAM 사용자**로 운영. `Admins` 그룹(`AdministratorAccess` 정책) 생성, 본인·협업자 각자 IAM 사용자를 그룹에 소속. **각자 개별 MFA 필수.** 장기 Access Key는 발급하지 않는 것이 원칙(CLI 필요 시 임시자격증명만, D4와 동일한 원칙을 사람 계정에도 적용). 이후 콘솔 로그인은 계정 별칭 URL + IAM 사용자로만, 루트는 사용 안 함. |
| **CloudTrail** | 멀티 리전 트레일 생성 완료(D2 "전 리전 수집" 충족). 관리 이벤트 읽기/쓰기 모두 활성화. 암호화는 **SSE-S3(기본, KMS 미사용)** — 비용·복잡도 회피, 17번의 "불변 감사로그(S3 Object Lock)"는 별도 버킷으로 추후 구성할 예정이라 이 트레일과는 분리된 개념. **로그 파일 검증 ON**(무료, 감사 완전성 KPI와 정합). **SNS 알림 OFF**(findings 흐름은 EventBridge 경로를 따로 씀), **CloudWatch Logs 연동 OFF**(필요해지면 추후 추가, 지금은 비용·운영 부담 최소화). 데이터 이벤트는 미설정(추후 필요 시 활성화). |

---

## Azure / Entra ID 초기 설정 — 미착수

> 아직 실제 설정 전. 아래는 데모 시작 전 완료해야 할 항목 목록.

| 항목 | 상태 | 메모 |
|---|---|---|
| 데모 전용 Entra 테넌트 or sandbox 구독 | 미착수 | 격리 환경 권장(target-app-design.md 6번 SP 스코프 주의) |
| App Registration — SSO 연동용 | 미착수 | Cognito SAML 연동, `cnapp-viewer`/`cnapp-approver` 그룹 생성 |
| App Registration — 과도권한 결함용 | 미착수 | Directory.ReadWrite.All 등 결함 시나리오용(격리 테넌트에만) |
| Service Principal — order 평문 시크릿용 | 미착수 | Directory.Read.All + Application.Read.All 스코프만. 만료일 = 데모+1주 |
| Defender for Cloud | 미착수 | 데모 기간만 활성, 이후 비활성 |
| Prowler Azure 스캔 권한(SP) | 미착수 | OCSF 출력 → S3 파이프라인 연동용 read-only SP |

---

## infra/shared (Terraform) — 미착수

- VPC, EKS, GitHub OIDC→IAM Role, NAT Instance(t3.nano), S3/DynamoDB Gateway Endpoint 등. **레포 = 모노레포 확정**(project-draft 24번), Terraform state는 `infra/{shared,target,console}`별 분리.

## infra/target — 미착수

## infra/console — 미착수

---

*항목이 새로 구축될 때마다 해당 섹션을 갱신한다. 설계 변경이 아니라 "실행 완료 여부" 기록이므로 docs/project-draft.md 등 설계 문서와는 별개로 관리한다.*
