# infra/console — 관제 앱 (프론트 + API + SSO)

> console-app-design §4·§7·§12 · project-draft §10(SSO)·§13. **shared 다음** 레이어.
> 관제 콘솔의 배포처 — 타깃 EKS와 **분리된 서버리스 환경**(§4 확정).

## 구성
```
[프론트]  apps/console 빌드 → S3(비공개) + CloudFront(OAC)
[인증]    Cognito User Pool ← Entra(SAML IdP) · custom:groups → viewer/approver(§7)
[API]     ALB(authenticate-cognito, HTTPS) → Lambda(apps/console-backend)
[데이터]  console-backend ↔ RDS pgvector(shared, VPC private subnet 배치)
[조치]    approver 승인 → console-backend가 engine Step Functions StartExecution(트리거만)
```

## 실 apply 전 채울 것 (TODO — 미정 시 빈값으로도 apply되나 SSO/HTTPS 미동작)
| 변수 | 무엇 | 출처 |
|---|---|---|
| `acm_certificate_arn` | ALB 443 인증서 (authenticate-cognito는 **HTTPS 필수**) | 도메인 + ACM 발급 |
| `saml_metadata_url` | Entra ID SAML 메타데이터 | 진우 Entra App Reg(SSO), manual-infra §3 |
| `remediation_state_machine_arn` | 조치 SM ARN | `infra/backend` output |
| console-backend `dist/` | Lambda 패키지 | `cd apps/console-backend && npm ci && npm run build` |

- `saml_metadata_url` 빈값이면 SAML IdP 없이 apply(로컬/데모 초기). 채우면 Entra 페더레이션 활성.
- `use_mock=false`(기본) = pgvector 실쿼리. 프론트는 `VITE_USE_MOCK=false` + `VITE_API_BASE=https://<alb_dns_name>/api`로 **MSW→실 API 무변 스왑**(§15.5).

## apply
```bash
cd apps/console-backend && npm ci && npm run build && cd -   # dist 빌드 선행
cd infra/console
terraform init && terraform validate
terraform apply \
  -var "acm_certificate_arn=arn:aws:acm:..." \
  -var "saml_metadata_url=https://login.microsoftonline.com/.../federationmetadata.xml" \
  -var "remediation_state_machine_arn=$(cd ../engine && terraform output -raw remediation_state_machine_arn)"
# 프론트 업로드:
#   cd apps/console && npm run build && aws s3 sync dist s3://$(terraform -chdir=../infra/console output -raw front_bucket)
terraform destroy
```

## 의존
- **선행:** `infra/shared`(VPC·RDS·Bedrock 정책). (선택) `infra/backend`(조치 SM ARN).
- **연동:** 진우 Entra App Reg(SSO SAML IdP) — SSO는 준형 Cognito ↔ 진우 Entra.
