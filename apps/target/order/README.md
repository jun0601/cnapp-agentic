# order 서비스 (타깃 앱 — retail-store orders fork)

골든 시나리오의 **측면이동 + 크로스클라우드 자격증명 탈취** 지점. product·member를 참조.

## 심는 결함

| 결함 | 위치 | control | 스캐너 |
|---|---|---|---|
| **f5 평문 Azure SP 시크릿** | `k8s/deployment.yaml` env | INTERNAL-SECRET-PLAINTEXT-001 | Prowler·매니페스트 스캔 |
| **f4 과도 IRSA(s3:\*)** | `infra/target` IAM 역할 | INTERNAL-IAM-OVERPRIV-001 | IAM Access Analyzer·Prowler |

> ⚠️ `deployment.yaml`의 Azure 자격증명 값은 **전부 가짜 placeholder**(실제 자격증명 아님). f5 결함(Secrets Manager 안 쓰고 파드 env에 평문)을 시연하기 위한 데모 전용.

## attack-path에서의 역할

```
product(f1 침투) ──R2 측면이동──▶ order(과도 IRSA f4)
                                     │
                    R3 자격증명 탈취(평문 Azure SP f5) ──▶ Azure Entra(신원 장악)
                                     │
                    R4 (order IRSA가 닿는) member 공개 S3 ──▶ AWS PII 탈취
```

- 앱 소스 = retail-store-sample-app orders 서비스 fork(product·member 참조만).
- 실제 SP는 **격리 데모 Entra 테넌트**에 `Directory.Read.All`+`Application.Read.All`만(manual-infra §3).
