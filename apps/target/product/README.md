# product 서비스 (타깃 앱 — retail-store catalog fork)

골든 시나리오의 **진입점**. 기능은 retail-store-sample-app의 catalog 그대로, **결함만 심는다**.

## 심는 결함

| 결함 | 위치 | control | 스캐너 |
|---|---|---|---|
| **f1 KEV 취약 이미지** | `Dockerfile`(낡은 베이스) | INTERNAL-VULN-KEV-001 | Trivy·Inspector |
| **f2 privileged/hostPath 파드** | `k8s/deployment.yaml` | INTERNAL-KSPM-PRIVILEGED-001 | kube-bench·trivy-k8s |

> ⚠️ 두 결함 모두 **데모 전용**. 실서비스 금지. 앱 로직은 upstream fork 그대로이며 여기선 결함 시연용 껍데기만 둔다.

## 참고

- 앱 소스 = [AWS retail-store-sample-app](https://github.com/aws-containers/retail-store-sample-app) catalog 서비스.
- 기능 개발에 시간 쓰지 않음(§7) — product는 "취약 이미지로 들어오는 입구" 역할.
- f1 이미지가 order로의 측면이동(R1→R2) 출발점(attack-path 노드 n1).
