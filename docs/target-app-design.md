# 타깃 앱 설계도 — 고객사 워크로드 (점검 대상)

> **문서 종류:** 타깃 앱 설계도 — 일부러 취약하게 만드는 고객사 워크로드(findings 소스)
> **목적:** 스캐너가 잡아낼 *의도적 결함(정답지)*과 그 결함들이 엮이는 골든 attack-path를 정의한다. "무엇을 어디에 심을지"의 구현 기준.
> **관련 문서:** 전체 방향·결정 → [project-draft.md](project-draft.md) · 이 findings를 표시하는 관제 앱 → [console-app-design.md](console-app-design.md)
> **읽는 순서:** project-draft 6·8번(멀티클라우드·앱 구조)을 먼저 본 뒤 이 문서로 결함 목록을 잡고, 관제 앱이 그 결함을 어떻게 보여주는지는 console 설계도로 넘어간다.
>
> 성격: 일부러 취약하게 설정된 "고객사 커머스". **findings의 소스**이자 골든 attack-path의 무대.
> 핵심 원칙 3가지:
> 1. **결함은 코드 버그가 아니라 인프라/설정(IaC)에 심는다** — CSPM/CIEM/KSPM/데이터가 잡는 건 설정이지 앱 로직이 아님.
> 2. **앱 기능은 최소, 결함은 풍부하게** — 기능을 늘리면 만들 게 늘 뿐, 점검 가치는 결함 다양성에서 나온다.
> 3. **관제 앱과 직접 통신하지 않는다** — 타깃 앱은 AWS 계정에 *배포*될 뿐, 점검은 스캐너가 계정을 read-only로 스캔(agentless). 섹션 5 참조.

---

## 1. 구성 🏗️ — 커머스 3 마이크로서비스 + Azure 신원 종착지

세 마이크로서비스와 Azure 신원 종착지의 기능·시나리오 역할을 정리한 표.

| 서비스 | 기능(최소) | 시나리오 역할 |
|---|---|---|
| `product` | 상품 목록/상세 조회 (공개 API) | 외부 노출 취약 워크로드 = **최초 침투 지점** |
| `order` | 주문 생성/조회 (상품·회원 참조) | 과도 권한 + **평문 시크릿에 Azure 자격증명** = 측면 이동·크로스클라우드 발판 |
| `member` | 회원 가입/조회 (PII 취급, **PII는 AWS S3에만 보관**) | 민감데이터 = **AWS PII 탈취 대상** |
| Azure Entra ID | 직원 신원 디렉터리 + App Registration(SSO 연동, 앱 아님) | **크로스클라우드 신원 장악 종착지**(과도권한 앱/계정 = 전체 통제권) |

> 기능은 평범한 CRUD면 충분. 상품 몇 개, 주문 흐름 한 줄, 회원 가입/조회. Claude Code로 빠르게 생성.
> **데이터는 AWS S3에만 둔다 — Azure에는 데이터를 두지 않는다(신원만).** Azure 종착지는 "데이터 노출"이 아니라 "신원 시스템 장악"이다.

---

## 2. 심는 결함 (정답지) 🔒 — 기둥별로 촘촘하게

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
| **평문 환경변수/매니페스트에 시크릿 — 그 안에 Azure 서비스 주체(SP) 자격증명** (Secrets Manager 미사용) | CSPM (+ **크로스클라우드 신원 경로의 핵심 발판**) |

### `member` — AWS 종착지
| 결함 | 잡는 도구(기둥) |
|---|---|
| 회원 데이터 S3 버킷 public access | Security Hub (CSPM) |
| 버킷 암호화 미설정 (KMS 없음) | CSPM |
| 버킷에 실제 민감 파일 (가짜 PII) | Macie (데이터) |
| ★ 버킷 버저닝/로깅 미설정 | CSPM |
| ★ 버킷 정책에 와일드카드 Principal | CSPM/CIEM |

### Azure Entra ID — 크로스클라우드 신원 종착지
> Azure에는 데이터를 두지 않는다. 결함은 전부 **신원(Entra ID)** 결함 — order에서 탈취한 Azure 자격증명이 이 결함들과 만나 "신원 시스템 장악"으로 이어진다.

| 결함 | 잡는 도구(기둥) |
|---|---|
| **과도권한 App Registration** (예: `Directory.ReadWrite.All` 등 디렉터리 광범위 권한) | Entra (CIEM) |
| **위험한 consent grant** (검증 안 된 앱에 광범위 위임 동의) | Entra (CIEM) |
| **Entra 권한상승 경로** (Service Principal/계정에 과도한 디렉터리 역할 할당) | Entra (CIEM) |
| **만료 없는/유출 위험 SP 자격증명** (order 평문 시크릿으로 노출되는 그 자격증명) | Entra (CIEM) |
| ★ (선택) Defender secure score를 깎는 일반 리소스 미스컨피그 | Defender for Cloud |

> 공통(전 서비스 적용 가능): CloudTrail 미설정 리전, 미사용 보안그룹, 태그 미설정 등 — secure score 깎는 잔결함은 자동으로 다수 발생(secure score 채점용).

---

## 3. 골든 attack-path (데모 하이라이트) — 크로스클라우드 신원 탈취

세 서비스 + Azure 신원이 한 줄로 꿰어진다. **단일 finding은 "중간 위험"인데, 묶으면 "Critical 신원 장악 경로"**가 되는 게 핵심.

```
[1] product 파드의 취약 이미지(KEV CVE)로 침투
      ↓ (Pod Security 위반 → 권한 확대)
[2] order 파드의 과도 IRSA 권한 탈취 + 평문 시크릿에서 Azure 자격증명 발견 → 측면 이동
      ↓ (s3:* 권한으로 / 손에 쥔 Azure SP 자격증명으로)
[3] member의 공개 S3 버킷 접근 → AWS PII 탈취
      ↓ (탈취한 Azure 자격증명을 사용)
[4] Azure Entra ID 접근 → 과도권한 App Registration/계정 장악
      = 크로스클라우드 신원 시스템 장악(디렉터리 전체 통제권)
```

LLM이 이 신호들(취약점+KSPM+CIEM+CSPM+데이터, **AWS 워크로드→Azure 신원**)을 **하나의 공격 서사로 엮는 것** = attack-path 내러티브 + "왜 LLM이냐"의 답.

> **구현 범위:** MVP는 "order의 평문 시크릿에 Azure 자격증명이 노출되면 → Azure 신원(Entra)까지 장악 위험"을 **분석·시각화**하는 수준까지다. 실제로 AWS에서 Azure로 횡단해 신원을 장악하는 **동작 구현은 보너스**(되면 데모). 정답지(심은 결함)와 그 상관 그래프만으로 차별점은 충분히 성립한다.

---

## 4. 결함 분포 요약 (6기둥 발화 확인)

각 기둥이 어느 서비스에서 발화하는지와 대표 결함을 한눈에 보여주는 표.

| 기둥 | 발화 서비스 | 대표 결함 |
|---|---|---|
| CSPM (설정) | order, member | 공개 S3 버킷, 열린 SG, 미암호화, 평문 시크릿 |
| CIEM (권한) | order(AWS), **Azure Entra** | 과도 IRSA·와일드카드 정책(AWS), **과도권한 App Registration·위험한 consent·권한상승(Azure)** |
| 취약점 | product | KEV CVE 이미지 |
| KSPM (K8s) | product | privileged 파드, root 실행 |
| 데이터 | member | 공개 S3 버킷의 PII (Macie, **AWS S3 전용**) |
| attack-path | 전체 | 1→2→3→4 **AWS 워크로드→Azure 신원** 크로스클라우드 경로 |

> 6기둥이 전부 최소 하나씩 발화하면서 서비스는 3개로 최소화. 각 기둥이 "왜 거기 있나"가 시나리오로 정당화됨. **데이터는 AWS S3에만, Azure는 신원(Entra)에만** 결함을 둬 역할이 깨끗이 갈린다.

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
- **배포:** EKS(product/order/member 파드) + S3(member PII 버킷) + Azure Entra ID(App Registration·SP, 데이터 저장소 아님). ArgoCD GitOps로 배포(트랙1 CI/CD).
- **Azure SP 스코프 주의:** order 파드에 심는 "평문 Azure SP 자격증명"은 실제 Entra SP. **`Directory.Read.All` + `Application.Read.All` 수준만 부여** — `Directory.ReadWrite.All` 등 쓰기 권한 절대 금지(실수로 사용 시 실제 테넌트 피해). **데모 전용 격리 테넌트**(별도 Entra 테넌트 또는 sandbox 구독 분리) 권장. SP 만료일 = 데모 종료일 +1주(만료 없는 SP 결함은 IaC 설정으로 시나리오상 심되, 실제 자격증명 자체에는 만료 적용).

---

*타깃 앱 설계도 — 메인 설계서(project-draft v5)의 8번 타깃 앱을 구현용으로 상세화. 결함 다양성↑, 기능 최소, agentless 연결 명시.*

*변경 요약: **Azure 종착지를 데이터(Blob)→신원(Entra ID)으로 전환.** Azure 결함을 과도권한 App Registration·위험한 consent·권한상승·SP 자격증명 노출로 교체, order에 "평문 시크릿 속 Azure 자격증명" 결함 추가. 골든 attack-path를 크로스클라우드 신원 탈취 경로([4] Entra 신원 장악)로 갱신, 결함 분포표도 동기화. 데이터(PII)는 AWS S3 전용·Macie도 S3 전용 명시. MVP는 분석·시각화 수준/횡단 동작은 보너스. 문서 식별 헤더 추가.*
