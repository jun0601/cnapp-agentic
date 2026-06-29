# 타깃 앱 설계도 — 고객사 워크로드 (점검 대상)

> 성격: 일부러 취약하게 설정된 "고객사 커머스". **findings의 소스**이자 골든 attack-path의 무대.
> 핵심 원칙 3가지:
> 1. **결함은 코드 버그가 아니라 인프라/설정(IaC)에 심는다** — CSPM/CIEM/KSPM/데이터가 잡는 건 설정이지 앱 로직이 아님.
> 2. **앱 기능은 최소, 결함은 풍부하게** — 기능을 늘리면 만들 게 늘 뿐, 점검 가치는 결함 다양성에서 나온다.
> 3. **관제 앱과 직접 통신하지 않는다** — 타깃 앱은 AWS 계정에 *배포*될 뿐, 점검은 스캐너가 계정을 read-only로 스캔(agentless). 섹션 5 참조.

---

## 1. 구성 — 커머스 3 마이크로서비스 + Azure 종착지

| 서비스 | 기능(최소) | 시나리오 역할 |
|---|---|---|
| `product` | 상품 목록/상세 조회 (공개 API) | 외부 노출 취약 워크로드 = **최초 침투 지점** |
| `order` | 주문 생성/조회 (상품·회원 참조) | 권한 오용 = **측면 이동 발판** |
| `member` | 회원 가입/조회 (PII 취급) | 민감데이터 = **AWS 최종 탈취 대상** |
| Azure Blob | 회원 데이터 분석본 보관 (앱 아님) | **크로스클라우드 탈취 종착지** |

> 기능은 평범한 CRUD면 충분. 상품 몇 개, 주문 흐름 한 줄, 회원 가입/조회. Claude Code로 빠르게 생성.

---

## 2. 심는 결함 (정답지) — 기둥별로 촘촘하게

> 진우 초안의 핵심 결함 + 각 기둥이 더 풍부하게 발화하도록 보강(★ = 보강분). 데모에선 일부만 켜도 되지만, 목록은 넉넉히.

### `product` — 침투 지점
| 결함 | 잡는 도구(기둥) |
|---|---|
| 취약 베이스 이미지 (오래된 CVE + **KEV 등재 1건**) | Trivy/Inspector (취약점) |
| 파드 Pod Security 위반 (privileged 또는 hostPath) | kube-bench (KSPM) |
| ★ 컨테이너 root 사용자 실행 | kube-bench (KSPM) |
| ★ 이미지 태그 `latest` 사용 (무결성 약점) | KSPM/공급망 |
| ★ ECR 이미지 스캔 미설정 | CSPM |

### `order` — 측면 이동
| 결함 | 잡는 도구(기둥) |
|---|---|
| 파드 IRSA 롤에 과도 IAM 권한 (`s3:*` 등) | IAM Access Analyzer (CIEM) |
| 보안그룹 0.0.0.0/0 인바운드 | Config/Prowler (CSPM) |
| ★ 미사용 권한 다수 (권한 creep) | IAM Access Analyzer (CIEM) |
| ★ 와일드카드 리소스(`Resource: *`) 정책 | CIEM |
| ★ 평문 환경변수에 시크릿 (Secrets Manager 미사용) | CSPM |

### `member` — AWS 종착지
| 결함 | 잡는 도구(기둥) |
|---|---|
| 회원 데이터 S3 버킷 public access | Security Hub (CSPM) |
| 버킷 암호화 미설정 (KMS 없음) | CSPM |
| 버킷에 실제 민감 파일 (가짜 PII) | Macie (데이터) |
| ★ 버킷 버저닝/로깅 미설정 | CSPM |
| ★ 버킷 정책에 와일드카드 Principal | CSPM/CIEM |

### Azure Blob — 크로스클라우드 종착지
| 결함 | 잡는 도구(기둥) |
|---|---|
| Storage public access 허용 + 민감 분석본 | Defender for Cloud (Azure CSPM) |
| ★ Storage 미암호화 / TLS 미강제 | Defender |
| ★ NSG 0.0.0.0 오픈 (VM 둘 경우) | Defender |
| ★ App Registration 과도 권한 | Entra (CIEM) |

> 공통(전 서비스 적용 가능): CloudTrail 미설정 리전, 미사용 보안그룹, 태그 미설정 등 — secure score 깎는 잔결함은 자동으로 다수 발생(secure score 채점용).

---

## 3. 골든 attack-path (데모 하이라이트)

세 서비스 + Azure가 한 줄로 꿰어진다. **단일 finding은 "중간 위험"인데, 묶으면 "Critical 탈취 경로"**가 되는 게 핵심.

```
[1] product 파드의 취약 이미지(KEV CVE)로 침투
      ↓ (Pod Security 위반 → 권한 확대)
[2] order 파드의 과도 IRSA 권한 탈취 → 측면 이동
      ↓ (s3:* 권한으로)
[3] member의 공개 S3 버킷 접근 → AWS PII 탈취
      ↓ (같은 데이터의 분석본이)
[4] Azure Storage 공개 Blob → 크로스클라우드로 PII 전량 노출
```

LLM이 이 신호들(취약점+KSPM+CIEM+CSPM+데이터, AWS→Azure)을 **하나의 공격 서사로 엮는 것** = attack-path 내러티브 + "왜 LLM이냐"의 답.

---

## 4. 결함 분포 요약 (6기둥 발화 확인)

| 기둥 | 발화 서비스 | 대표 결함 |
|---|---|---|
| CSPM (설정) | order, member, Azure | 공개 버킷, 열린 SG, 미암호화 |
| CIEM (권한) | order, Azure | 과도 IRSA, 와일드카드 정책 |
| 취약점 | product | KEV CVE 이미지 |
| KSPM (K8s) | product | privileged 파드, root 실행 |
| 데이터 | member | 공개 버킷의 PII (Macie) |
| attack-path | 전체 | 1→2→3→4 크로스클라우드 경로 |

> 6기둥이 전부 최소 하나씩 발화하면서 서비스는 3개로 최소화. 각 기둥이 "왜 거기 있나"가 시나리오로 정당화됨.

---

## 5. 연결 구조 (★ 중요 — API 직접 연결 아님)

타깃 앱과 관제 앱은 **서로 직접 통신하지 않는다.** CSPM은 agentless — 앱에 아무것도 안 심고, 클라우드 계정을 바깥에서 read-only로 스캔한다.

```
타깃 앱 (고객사)                     관제 앱 (우리)
   │                                   │
   │ AWS/Azure 계정에 배포됨            │ findings 저장소를 읽는 대시보드
   ▼                                   ▲
[ 클라우드 계정의 설정/리소스 ]         │
   │  ▲                                │
   │  │ read-only 스캔(agentless)       │
   ▼  │                                │
[ 스캐너: Config·Prowler·Inspector·    │
   Trivy·kube-bench·Macie·Defender ]   │
   │                                   │
   ▼                                   │
[ findings ] → EventBridge→SQS→Lambda → OCSF 정규화 → 벡터DB/엔진 ─┘
```

**API가 존재하는 곳:**
- 스캐너 ↔ AWS/Azure API (계정 설정 읽기) — read-only IAM 역할/자격증명
- 관제 앱 프론트 ↔ 우리 백엔드 API (findings 조회) — 우리 시스템 내부

**타깃 앱과 관제 앱 사이 직접 API는 없음.** 타깃 앱은 자기가 점검당하는지도 모름 — 그냥 클라우드에 배포되어 있고, 스캐너가 계정을 바깥에서 읽을 뿐.

> 이 구조라서 타깃 앱이 무엇이든 상관없다(가져다 써도 됨). 관제 앱은 타깃 앱 내부를 모르고, findings 저장소만 읽는다.

---

## 6. 구현 메모

- **앱 코드:** aws-samples 계열 컨테이너 데모 베이스 + Claude Code로 부족분 생성. 기능 개발에 시간 쓰지 않음.
- **결함:** Terraform/k8s 매니페스트에 의도적으로 심음. CloudGoat/AWSGoat/Terragoat 패턴 참고(정답지가 명확해짐).
- **결함 토글:** 결함을 모듈/변수로 켰다 껐다 가능하게 → "결함 있을 때 잡히나 / 고치면 사라지나" 테스트 + 다양한 조합 attack-path 테스트.
- **golden findings 세트:** 심은 결함 목록 = 기대 findings. CI에서 "전부 탐지됐나" 자동 회귀 테스트.
- **배포:** EKS(product/order/member 파드) + S3(member 버킷) + Azure Storage. ArgoCD GitOps로 배포(트랙1 CI/CD).

---

*타깃 앱 설계도 — 메인 설계서(project-draft v5)의 8번 타깃 앱을 구현용으로 상세화. 결함 다양성↑, 기능 최소, agentless 연결 명시.*
