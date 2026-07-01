# apps/target — 취약 타깃 앱 (findings 소스)

일부러 취약하게 만든 "고객사 워크로드". 스캐너가 이 앱이 배포된 클라우드를 read-only로 훑어
findings를 만들고, 그게 관제 앱(apps/console)에 뜬다. **타깃 앱과 관제 앱은 직접 통신 안 함(agentless).**

> 원칙(target-app-design §7): **기능 최소, 결함 다양성 최대.** 결함은 앱 코드 버그가 아니라
> **인프라/설정(IaC)·이미지·매니페스트**에 심는다. 기능 베이스 = AWS retail-store-sample-app.

## 서비스 3종

| 서비스 | 베이스 | 스택 | 역할(골든) |
|---|---|---|---|
| `product` | retail-store catalog fork | (upstream) | 진입점 — KEV 취약 이미지 |
| `order` | retail-store orders fork | (upstream) | 측면이동 + Azure 자격증명 탈취 |
| `member` | **신규 작성** | **Python/FastAPI** | AWS 데이터 탈취 종착지 — PII seeder |

## 결함 ↔ 위치 매핑 (정답지)

| 결함 | control | 위치 | 스캐너 |
|---|---|---|---|
| f1 KEV 취약 이미지 | INTERNAL-VULN-KEV-001 | `product/Dockerfile` | Trivy·Inspector |
| f2 privileged/hostPath 파드 | INTERNAL-KSPM-PRIVILEGED-001 | `product/k8s` | kube-bench·trivy-k8s |
| f3 열린 SG(0.0.0.0/0) | INTERNAL-SG-OPEN-INGRESS-001 | `infra/target` | SecurityHub·Prowler |
| f4 과도 IRSA(s3:\*) | INTERNAL-IAM-OVERPRIV-001 | `infra/target` | Access Analyzer·Prowler |
| f5 평문 Azure SP 시크릿 | INTERNAL-SECRET-PLAINTEXT-001 | `order/k8s` env | Prowler·매니페스트 스캔 |
| f6 공개 S3 버킷 | INTERNAL-S3-PUBLIC-001 | `infra/target` | SecurityHub·Config·Prowler |
| f7 S3 PII(합성) | INTERNAL-DATA-PII-EXPOSED-001 | `member` seeder + `infra/target` 버킷 | Macie |

> f12(ECR 스캔 off)·f16(Azure SP)는 각각 `infra/shared`·격리 Entra 테넌트(manual-infra §3)에 위치.

## 배포 (개요)

- 이미지 → ECR(`infra/shared`) → EKS(`namespace: shop`)에 ArgoCD GitOps로 배포.
- 인프라 결함(S3·SG·IRSA)은 `infra/target`이 apply(휘발성·격리, 데모 후 destroy).
- 데모 종료 시 `terraform destroy` + 이미지 정리(무료티어 가드레일).

## ⚠️ 안전

- 모든 시크릿/PII는 **가짜(faker/placeholder)** — 실제 자격증명·개인정보 없음.
- 결함은 **격리된 데모 환경 전용**. Azure는 별도 데모 테넌트(실 조직 테넌트 금지).
