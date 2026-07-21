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

## apply 입력값 (전부 확보 완료 — 라이브 검증됨)
| 변수 | 무엇 | 출처 | 상태 |
|---|---|---|---|
| `acm_certificate_arn` | ALB 443 인증서 | 도메인 + ACM 발급 | ✅ 서울·us-east-1 둘 다 ISSUED |
| `saml_metadata_url` | Entra ID SAML 메타데이터 | 진우 Entra App Reg, manual-infra §3.6.1 | ✅ 반영됨 |
| `remediation_state_machine_arn` | 조치 SM ARN | `infra/backend` output | ✅ |
| console-backend `dist/` | Lambda 패키지 | `cd apps/console-backend && npm ci && npm run build` | ✅ (apply 전 빌드 필수) |

- ⚠️ **`enable_custom_domain` 기본값은 `false`** — 무인자 apply는 커스텀 도메인·SPA Cognito 클라이언트를 **만들지 않는다**(이미 있으면 파괴). 라이브 재현 시 `-var enable_custom_domain=true` 필수.
- ⚠️ **재apply(fresh)마다 Cognito Pool ID·SPA client ID가 새로 발급**된다 → SPA 재빌드(`VITE_COGNITO_CLIENT_ID`) + **Entra 앱 식별자를 `urn:amazon:cognito:sp:<새 Pool ID>`로 수동 갱신**해야 로그인이 된다(manual-infra §5).
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
  -var "remediation_state_machine_arn=$(cd ../backend && terraform output -raw remediation_state_machine_arn)"
# 프론트 업로드:
#   cd apps/console && npm run build && aws s3 sync dist s3://$(terraform -chdir=../infra/console output -raw front_bucket)
terraform destroy
```

## 의존
- **선행:** `infra/shared`(VPC·RDS·Bedrock 정책). (선택) `infra/backend`(조치 SM ARN).
- **연동:** 진우 Entra App Reg(SSO SAML IdP) — SSO는 준형 Cognito ↔ 진우 Entra.
