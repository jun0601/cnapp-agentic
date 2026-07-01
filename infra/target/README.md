# infra/target — 의도적 결함 IaC (⚠️ 격리·데모 전용)

취약 타깃 앱이 배포될 인프라 결함을 Terraform으로 심는다. **일부러 취약**하므로 격리 환경에서
데모 기간에만 apply하고 끝나면 `destroy`한다(무료티어 가드레일).

## 심는 결함 (토글)

| 토글(var) | 기본 | 결함 | control |
|---|---|---|---|
| `enable_s3_public` | false | f6 member PII 버킷 공개 | INTERNAL-S3-PUBLIC-001 |
| `enable_open_sg` | false | f3 0.0.0.0/0 열린 SG | INTERNAL-SG-OPEN-INGRESS-001 |
| `enable_overpriv_irsa` | false | f4 order IRSA s3:* | INTERNAL-IAM-OVERPRIV-001 |

> 기본은 **전부 off(안전)**. 데모 시 `-var enable_s3_public=true` 식으로 켠다. 개별 토글이라
> "이 결함만 켜고 스캐너가 잡나" 회귀 테스트가 쉽다(§7 권장).
>
> f7(PII 데이터)은 이 버킷에 `member` seeder가 적재. f1·f2·f5는 앱 쪽(`apps/target`),
> f12는 `infra/shared`, f16은 격리 Entra 테넌트(manual-infra §3).

## 선행 / 실행

- 선행: `infra/shared` apply 완료(VPC·OIDC provider 출력 참조 — `terraform_remote_state`).
- ```bash
  terraform init   # backend=cnapp-agentic-tfstate, key=infra/target
  terraform plan  -var enable_s3_public=true -var enable_open_sg=true -var enable_overpriv_irsa=true
  terraform apply ...
  # 데모 후
  terraform destroy
  ```

## ⚠️ 안전

- 실제 자격증명·개인정보 없음(seeder는 faker 합성). 
- 절대 프로덕션/공용 계정에 apply 금지 — 격리 데모 계정 전용.
- `default_tags`에 `Warning=intentionally-vulnerable-demo` 부착(오인 방지).
