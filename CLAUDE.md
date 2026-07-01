# CLAUDE.md

> 이 파일은 Claude Code(및 협업자)가 이 레포에서 작업할 때 가장 먼저 읽는 기준 문서다.
> 상세 설계는 [docs/project-draft.md](docs/project-draft.md)(메인 설계서 v5), [docs/target-app-design.md](docs/target-app-design.md)(타깃 앱 상세), [docs/console-app-design.md](docs/console-app-design.md)(관제 앱 상세)에 있다. **이 셋이 단일 진실 공급원(SSOT)이며, 본 문서는 그 요약 + 협업 규칙이다.**

---

## 0. 작업 규칙 (모든 클로드·협업자가 지킬 것) ⚡

1. **시작 전:** 어떤 작업이든 시작 전 반드시 이 **CLAUDE.md를 먼저 읽고**, `git pull`로 최신 main을 받는다.
2. **변경 로그 기록:** 작업 중 중요한 변경·결정·방향 전환이 생기면 아래 [변경 로그](#변경-로그-최신이-위로)에 한 줄로 남긴다. *사소한 수정(오타·포맷 등)은 적지 않는다 — 다른 사람이 알아야 할 것만.*
3. **`[PULL 필요]` 태그:** 상대가 반드시 pull해야 할 중요 변경(설계 방향 전환, 핵심 결정, 구조 변경)은 변경 로그에 **`[PULL 필요]`** 태그를 붙여 명시한다.
4. **작업 후:** `commit` + `push`로 공유한다(커밋 메시지 `타입: 내용`). 상세 협업 규칙은 [6번](#6-협업-규칙-) 참조.
5. **작업 로그 기입:** 구현하며 겪은 문제·해결과 추가·작업한 것은 루트의 **[troubleshooting.md](troubleshooting.md)** 에 한 줄씩 남긴다(중앙 1개 파일, 영역별 파일 금지). 형식 `YYYY-MM-DD / 작성자 / [영역] / 내용`, 영역 태그 `[infra]` `[scanners]` `[pipeline]` `[engine]` `[rag]` `[attackpath]` `[apps-target]` `[apps-console]` `[contracts]` `[docs]` `[ci]`. *굵직한 설계 변경*은 여기 말고 위 변경 로그에(목적 분리: troubleshooting=작업 디테일, 변경 로그=pull 알림).
6. **진척 갱신:** 굵직한 진척(영역 완료·다음 착수 변경)이 생기면 **[§7.1 현황+다음](#71-현황--다음-할-일-next-up--진행-관리-단일-지점-작업-후-여기부터-갱신)**을 갱신한다(진행 관리 단일 지점 — "지금 어디까지/다음 뭐"를 여기서 관리).

### 변경 로그 (최신이 위로)

> 형식: `날짜 / 작성자(준형·진우) / 한 줄 요약 / (필요 시 [PULL 필요])`. 최근 10~15개만 유지하고 오래된 항목은 [아카이브](#변경-로그-아카이브)로 내린다.

- **2026-07-01 / 준형 / 폴더 규칙 명문화(하위 최소화·소유자별 2개) + engine 재구성** — 누락됐던 규칙 복원: **하위 폴더는 소유자별 2개(a=준형·b=진우)로 최소화, 공유 코드만 예외 폴더**(사람 이름 폴더는 여전히 금지 — 이름은 컴포넌트로). project-draft §4.6·CLAUDE §4에 반영. engine을 `core`(공유)+`triage`+`evidence`(과다 분할)에서 **`core`(공유) + `evidence`(준형: triage.py·evidence.py)** 2폴더로 합침(진우 몫 `reasoning/`는 예정). run_demo 재실행 통과. **`[PULL 필요]`**
- **2026-07-01 / 진우 / Azure/Entra ID 초기 설정 완료 — `cnappagentic.onmicrosoft.com` 테넌트·Teams 웹훅** — M365 Business 체험으로 `cnappagentic.onmicrosoft.com` 데모 전용 테넌트 생성. 관리자 계정(jw_kim·jh_lee Global Admin), 보안 그룹(cnapp-viewer·cnapp-approver), 데모 계정(viewer@·approver@) 생성 완료. Teams `cnapp-agentic` 워크스페이스·`cnapp-alerts` 채널·Workflows 웹훅 URL 발급. `manual-infra.md §3` 갱신. 미착수: App Registration(SSO·CIEM)·SP·Defender for Cloud. **`[PULL 필요]`**
- **2026-07-01 / 준형 / 엔진 Evidence·Triage 목업 능동조사 구현(`engine/`) — 데모 심장 1차** — `python -m engine.run_demo`로 **트리아지 게이트(20→12 승급, 비용통제) → Evidence가 계약④ allowlist 강제하며 read-only 툴 4회 자가 호출(챗봇 탈출) → confirmed 판정 → case(계약⑦) 검증**까지 재현. **MockToolExecutor·규칙 플래너**라 `RealToolExecutor`(boto3)·Bedrock LLM으로 갈아끼우면 실AWS 전환(Evidence/Triage 로직 무변 — 계약이 SSOT라 스왑 매끄러움). 담당: 준형=Triage·Evidence / 진우=Hypothesis·Reasoning. 독립 리뷰 반영(타임스탬프 timedelta·검증 강화·가드). **`[PULL 필요]`**
- **2026-07-01 / 준형 / 진행 관리 단일 지점 = §7.1 확정 + 하이브리드 진행 원칙 + README 역할분담 순서·진행상황** — §7.1을 낡은 "다음 착수 계획"에서 **"현황 + 다음 할 일"** 트래커로 갈아엎음("지금 어디까지/다음 뭐"를 여기서 관리, 큰 그림은 README). §0에 규칙 6(진척 시 §7.1 갱신) 추가. **진행 원칙 = 하이브리드**: 빌드 순서는 인프라 먼저지만 **목업 우선으로 논리 병렬** + **리스크 큰 실검증(엔진 실 tool-use·스캐너 1개→실 finding)은 실클라우드 조기 검증(apply→테스트→destroy 사이클)** (free credit 감안, 상시 방치 금지). README **역할 분담을 진행 순서(①앱&환경 → ⑦attack-path)로 재배치 + 진행상황 컬럼** 추가(①앱&환경: 준형 앱2개 / 진우 M365·Entra 테넌트). **`[PULL 필요]`**
- **2026-07-01 / 진우 / Cognito SSO 설계 검증 3건 수정 반영** — ① `authenticate-oidc` → `authenticate-cognito` 전면 교체(project-draft §10·아키텍처 다이어그램, console-app-design §4·§7·§15 전 위치 — Cognito 전용 액션이 더 단순하고 클라이언트 시크릿 불필요). ② **Identity Pool 제거** — 프론트가 AWS를 직접 호출하지 않으므로 User Pool만으로 충분, infra/console에서 만들 필요 없음. ③ **console-app-design §7 그룹 클레임 매핑 경로 추가** — Entra SAML attribute→Cognito `custom:groups`→`x-amzn-oidc-data` JWT→Lambda viewer/approver 분기. **`[PULL 필요]`**
- **2026-07-01 / 준형 / 타깃 앱(`apps/target`) + `infra/target` 결함 IaC 구현 + 콘솔 스텁 4화면 완성 — 독립 리뷰 2회 반영** — **타깃 앱:** member=**Python/FastAPI 확정**(§7 피드백 닫음, `apps/target/member` REST + **PII seeder**=faker 한국형 합성 rrn→S3, Macie 미끼) / product(f1 KEV 이미지·f2 privileged) / order(f5 평문 Azure SP=가짜값) k8s 매니페스트 + namespace `shop`. **`infra/target`:** 결함 IaC 토글(`enable_s3_public` f6·`enable_open_sg` f3·`enable_overpriv_irsa` f4, 기본 off), remote_state로 infra/shared OIDC 참조, **IRSA `:aud`+`:sub` 역할별 고정**. 리뷰 반영: infra/shared에 `eks_oidc_provider`(URL) 출력 추가(target 참조 정합), IRSA sub 조건, botocore ClientError. **콘솔 스텁:** Login(SSO 흐름·역할선택)·Audit(골든 타임라인 12건·필터·불변)·Compliance(ISMS-P↔control 매핑·충족률)·Remediation(실 finding 연동·approver 게이트). **모든 시크릿·PII는 가짜**(격리 데모 전제). py_compile·terraform fmt·tsc·vite build 전부 통과. **`[PULL 필요]`**
- **2026-07-01 / 준형 / `apps/console` 스캐폴드 착수 — 관제 앱 골격(목업 우선, 빌드 통과)** — §15 청사진대로 **Vite+React+TS+Tailwind+TanStack+React Flow+Recharts+MSW** 스캐폴드. **contracts가 타입 SSOT**(types.ts 손번역 + `gen-types.mjs` 재생성), **MSW handlers가 `@contracts` alias로 `mock-*.json` 직접 서빙**(vite `fs.allow`=repoRoot) → **백엔드·AWS 0으로 전 화면 동작**. 화면 8종(핵심 4=Dashboard·Findings·**FindingDetail[Evidence 탭=능동조사 UC0]**·AttackPath[React Flow AWS/Azure 레인] + 스텁 4). API 표면(§15.2)·화면↔mock(§15.4) 배선. `npm i`(252pkg)·`msw init`·`tsc --noEmit`·`vite build`(499 모듈) 전부 통과. 실행: `apps/console`에서 `npm run dev`. 다음 = 실 화면 다듬기·나머지 화면·(엔진 나오면) MSW off 스왑. **`[PULL 필요]`**
- **2026-07-01 / 준형 / 진우 문서 검증 6건 총괄 반영 — 전 md stale 스윕 + README 역할분담 신설(카탈로그 14종)** — ① **CLAUDE §5 앱 분담 stale**(진우 0b1d493 병합 때 옛 행으로 되돌아감) → "타깃+관제 2개 모두 준형 전담"으로 정정. ② **project-draft §4.4.1(b) 카탈로그 표** 누락분 4행 추가(ENTRA-SP-CRED·ENTRA-INSECURE-CFG·ECR-SCAN + 신규 S3-LOGGING) → **13→14종**, README·contracts/README 계수 일괄 갱신. ③ **console §3·§5.1** "D3/Recharts" → **React Flow**(§15.1 확정). ④ **f15 title↔control 모순**(NOENCRYPT인데 source는 버저닝) → 신규 `INTERNAL-S3-LOGGING-DISABLED-001`(cspm) 추가 후 재매핑. ⑤ **§15 모델 ID**: `claude-haiku-4-5`는 Anthropic 별칭·**Bedrock invoke ID 아님(404)** → Bedrock 형식/서울 inference profile 구현 시 확정 주석. ⑥ **R1 "同 resource" 모호**(KEV 파드 vs open SG는 resource_id 다름) → "워크로드↔부착 SG 토폴로지 인접"으로 완화 + 파드→ENI→SG 매핑·mock 선언 주석. **README에 "역할 분담(2인)" 섹션 신설**("관제 앱"=준형 / "운영 관제"=진우 구분 명시). validate 통과(14종). **`[PULL 필요]`**
- **2026-07-01 / 준형 / contracts f16·f12 객관 기준 최종 확정(진우 합의) — 카탈로그 13종 복구** — ① **f16** → `OVERPRIV-APP-001`(의미 느슨: "과도권한 앱"인데 finding은 "SP 자격 무만료")을 `INTERNAL-ENTRA-SP-CRED-001`(ciem, title 정확 일치)로 재매핑 + **카탈로그에 SP-CRED-001 재추가**(11→13, 병합 중 유실분 복구). ② **f12/ECR** → pillar `vuln`→`cspm`(control도): "scan-on-push 비활성"은 CVE가 아니라 **미스컨피그**이고 소스가 전부 posture(`securityhub:ECR.1`·`config`·`prowler:ecr_*_scan_*`)라 cspm이 객관 — vuln 기둥은 실 CVE(Inspector/Trivy) 전용으로 유지. validate 통과. **원칙 = "기둥(pillar)은 finding을 만드는 소스의 성격으로 판정"**(처음부터 일관 적용). **`[PULL 필요]`**
- **2026-07-01 / 준형 / 진우 커밋(0b1d493) contracts 리그레션 2건 수정 — main RED→GREEN** — pull 후 `validate.py` 2건 FAIL 발견: ① **f5** `resource_id`가 `aws:eks_pod:shop/order`로 리버트돼 `resource_type`(secret_plaintext)와 assert(b) 불일치 → 다시 `aws:secret_plaintext:shop/order/AZURE_SP_CRED`로 복원(c463054 교정본). ② **f17**이 `ENTRA-RISKY-CONSENT-001`(ciem)로 재매핑됐으나 pillar `cspm` 유지 → assert(a) 위반. **설계 충실**(Azure Defender secure-score=cspm 축) 방향으로 `INTERNAL-ENTRA-INSECURE-CFG-001`(cspm) 카탈로그 재추가 후 f17 재매핑. validate 통과. ※진우의 **f16→OVERPRIV-APP-001 재매핑**은 CI-green이나 SP-cred-no-expiry↔over-priv-app 의미가 느슨 — **진우 검토 요청**. **`[PULL 필요]`**
- **2026-07-01 / 준형 / console 외부 리뷰 반영 — Evidence 탭 소스 이중성 해소 + 스택 확정** — UC0(Evidence·판정)=**case 단위**, UC1(설명)=**finding 단위**로 확정: `finding_explanations`에서 `evidence_json` 제거·`case_id` FK 추가, **`cases` 테이블 신설**, 상세는 `finding_id∈case.finding_ids` 조인(§5·§6·§15). `ai_status`≠done placeholder 규칙 명시(AI 죽어도 finding 표시). §15 스택 **확정**: attack-path=React Flow·목업=MSW·console-backend=TypeScript + **폴리글랏(console=TS / engine·pipeline=Python)**. → 이 커밋 후 apps/console 스캐폴딩 착수 OK. **`[PULL 필요]`**
- **2026-07-01 / 준형 / 앱 2개 구현 청사진 신설(피드백→코딩 흐름)** — 코딩 전에 "어떻게 만들지"를 설계 문서에 박음: **console §15**(Vite+React+TS·TanStack·Tailwind·React Flow·MSW 목업·contracts→TS 타입, API 표면, 폴더구조, 화면↔mock 1:1, 데모 동선) + **target §7**(retail-store fork+커스텀 member, 취약 이미지, 결함 f1~f9↔IaC 토글 매핑, 폴더구조, 배포·회귀). 각 절에 피드백 요청 포인트 명시 → 리뷰 후 착수. **`[PULL 필요]`**
- **2026-07-01 / 준형 / 프로젝트 명칭 확정 → §24 전부 닫힘** — 명칭 = "에이전틱 AI 기반 멀티클라우드 CNAPP 보안 플랫폼"(잠정), 레포 = `cnapp-agentic`. **열린 설계 미확정 0건**(UC5 PDF는 console 보너스).
- **2026-07-01 / 준형 / target-app-design §2.1을 "할 일→완료"로 정정 + §2.0 SP행 추가** — §2.1 제목·본문을 *완료형*("validate.py가 강제")으로 교체(이미 c463054에서 처리된 걸 미완 TODO로 오해 방지). §2.0 표 f5 행을 실제 캐논 resource_id로·골든 편입된 f16(SP, 노드 n4) 행 추가(골든 10건). §6 결함 메모의 "AWSGoat 참고"를 §1.1(AWSGoat 미사용)과 일관되게 TerraGoat/CloudGoat/EKS Goat로 정정. (문서 정합만, 코드 변경 없음)
- **2026-07-01 / 준형 / contracts 계약 정합 4건 수정(target-app-design §2.1 닫음) + validate.py CI 게이트** — ① f5 `resource_id`를 캐논 위반(`aws:eks_pod:…`+type secret_plaintext) → `aws:secret_plaintext:shop/order/AZURE_SP_CRED`로 교정(4.4.1a 예시도 갱신). ② 의미 안 맞는 id 재사용 해소 — 신규 control 3종(`INTERNAL-ECR-SCAN-DISABLED-001`·`INTERNAL-ENTRA-SP-CRED-001`·`INTERNAL-ENTRA-INSECURE-CFG-001`)을 카탈로그에 추가하고 f12/f16/f17 재배정. ③ **f16(Azure SP)을 골든 경로에 편입** — attack-path 노드 n4에 대응 finding이 없던 빈틈을 메움(assert c 충족). ④ `contracts/validate.py`(4-assert: pillar·resource_id↔type·node-finding·dedup_key) + `.github/workflows/contracts-validate.yml` CI 게이트 신설. 검증 통과. **`[PULL 필요]`**
- **2026-07-01 / 준형 / 타깃 앱 기능 베이스 확정(retail-store-sample-app) + 정답지 contracts 매핑** — target-app-design §1.1 신설: 기능 껍데기 = **AWS retail-store-sample-app**(catalog·orders 2서비스 + 커스텀 member), AWSGoat 미사용·goat류는 패턴 참고만. §2.0 **정답지=contracts 매핑표**(골든 9건↔리소스·control_id), §2.1 **계약 정합 체크리스트 4건**(f5 resource_id↔type 불일치, control 3종 신규 추가, 검증기 4-assert CI 게이트화) — *이건 contracts 구현 전 고칠 후속*. **`[PULL 필요]`**
- **2026-07-01 / 준형 / `infra/shared` 스캐폴드 착수(레이어드 0번)** — VPC(NAT Gateway 끔 + S3·DynamoDB Gateway Endpoint)·**raw NAT Instance**(t4g.nano, fck-nat AMI)·EKS(spot t3.small·scale 0~2·IRSA·access entry)·ECR 4종·**RDS PostgreSQL t3.micro+pgvector**(private·Secrets Manager)·**GitHub OIDC**(키 없음)·**Evidence read-only 정책**(contracts/evidence-allowlist.json과 1:1)·Bedrock invoke 정책. `terraform fmt`·`validate` 통과. **apply는 게이트 후**(state 버킷 부트스트랩·Bedrock 모델 액세스·TODO 마커·fck-nat AMI 계정 검증). **`[PULL 필요]`**
- **2026-07-01 / 진우 / project-draft §4.4 2-pass 트리거 이벤트 연쇄 확정** — attack-path Lambda 완료→Triage Lambda 기동 사이 누락 이벤트 발견·보완: `cnapp.attackpath.correlation.completed` 이벤트 명시(DB upsert 완료 후 발행 → Triage 구독, `attack_path_id!=null` 조건 유효성 보장). **`[PULL 필요]`**
- **2026-06-30 / 준형 / `contracts/` 졸업 — 계약 7종 *.json + control-catalog + mock 데이터 생성** — 산문(4.4/4.4.1) → 실제 JSON Schema(draft 2020-12) 졸업: `finding`·`case`·`attack-path`·`evidence-allowlist`·`ingest-envelope`·`rag-chunk` 스키마 + `control-catalog.json`(INTERNAL control 10종). 목업: `mock-findings.json`(20건, 골든 9건 체이닝, open/remediated/suppressed 혼합)·`mock-attack-paths.json`(골든 1경로, 4 엣지 type·cross_cloud)·`mock-cases.json`(엔진 능동조사 한 장면, Evidence 4회). JSON 유효성·교차참조 정합 검증 통과. **이제 양쪽 병렬 가능** — 진우는 이 목업으로 콘솔, 준형은 infra/shared. **`[PULL 필요]`**
- **2026-06-30 / 준형 / 검증 후속 전부 확정 + README 폴더구조 갱신** — 진우 "피드백 없음" → 대기 항목 확정: **4.4.1 정규화 규칙 3종**(`resource_id` 캐논 표·INTERNAL `control_id` 카탈로그·remediated source별 스코프) 신설하고 §24 3건 닫음, attack-path **2-pass**·**핵심 영역 분담** 전부 `확정`으로 전환(§5/4.1). README를 실제 폴더구조(contracts·scanners·pipeline·rag·attackpath·troubleshooting)로 갱신 + docs 안내 dead-link(infra-status→manual-infra) 수정. **`[PULL 필요]`**
- **2026-06-30 / 준형 / CLAUDE.md §6·§7 복구(머지 유실) + §5 손상 수정 + §7.1 Next Up 계획 추가** — `HEAD~4` 머지에서 §6 협업규칙·§7 작업기준이 날아가고 §5 "시간 컷" 불릿이 깨진 채 잘렸던 것 복원(§0의 §6 dead-link 해소). §7.1에 합의된 다음 착수 계획 신설: **착수=둘 동시(contracts+infra 병렬), 데모 컷=절대사수 풀세트, Azure 격리 테넌트=진우 확보.** **`[PULL 필요]`**
- **2026-06-30 / 준형 / attack-path↔Evidence 순서 2-pass로 통일 + 검증 피드백 3건 미확정 등록** — UC0(§9)와 진우의 트리거/게이트가 상충(Evidence→상관 vs 상관→Evidence)하던 걸 **2-pass**(① 1차 규칙상관이 `attack_path_id` 부여 → ② 트리아지 게이트 → ③ Evidence 증거수집 → ④ 2차 확정·내러티브)로 통일. 추가 검증에서 ①`resource_id` 정규화 규칙 ②INTERNAL `control_id` 카탈로그·매핑 ③remediated 스코프(스캐너별) 미정 발견 → §24 등록(contracts 졸업 시 진우와 확정). `severity_id` 주석 오류("OCSF식" → 내부 컨벤션, 실제 OCSF와 반대) 정정. **`[PULL 필요]`**
- **2026-06-30 / 진우 / 설계 미확정 9개 항목 전부 닫음** — ① D4 Azure 키리스 인증(Entra Workload Identity Federation) 확정 ② 트리아지 게이트 임계값(`severity_id≤2` OR `attack_path_id!=null`) ③ 자동 조치 카탈로그 MVP 3종(S3 block·SG 제거·IAM diff) ④ 임베딩 모델 Titan v2 서울 확인·fallback(Cohere Embed Multilingual v3) ⑤ RDS 자동재시작 방지(EventBridge Scheduler+Lambda) ⑥ Prowler Azure cron(`0 17 * * *`) ⑦ attack-path 트리거(배치 완료 EventBridge 이벤트) ⑧ §24 타깃앱 세부·자동조치 체크박스 ⑨ console §14 동기화. project-draft·console-app-design·manual-infra 동기화. **`[PULL 필요]`**
- **2026-06-30 / 준형 / project-draft 17~24번 섹션 복구(유실 사고 수정)** — `cb2c55a`(이음새 계약 커밋)에서 거버넌스(17)·Shift-Left(18)·테스트(19)·KPI(20)·로드맵(21)·비용 가드레일(22)·확장(23)·미확정(24)이 실수로 삭제됐던 것을 `53f8bd6`(v5.4)에서 추출해 복원. console 설계서가 참조하던 17/19/21/24 dead-link 해소. **`[PULL 필요]`**
- **2026-06-30 / 준형 / 작업 로그(troubleshooting.md) 신설 + 레포 구조 트리 갱신** — 루트에 **`troubleshooting.md`** 생성: 트러블슈팅 + 진행 로그를 **중앙 1개 파일**에 `[영역]` 태그로 한 줄씩(영역별 파일 금지 — 스프롤·교차패턴 손실 방지). 작업규칙 5번에 기입 형식 명시. CLAUDE 4번 폴더트리를 실제 구조(contracts·scanners·pipeline·rag·attackpath·manual-infra 포함)로 갱신, project-draft 4.6과 정합. **`[PULL 필요]`**
### 변경 로그 아카이브

> 15개 초과 항목을 아래로 이동.

- **2026-06-30 / 준형 / 이음새 계약 3종 추가 + terraform 레이어링·폴더소유 확정(4.6)** — 반반 분담으로 드러난 이음새를 계약으로 박음: **⑤ 수집 봉투** **⑥ 임베딩 모델+rag_chunk** **⑦ 엔진 case 핸드오프**(트리아지 게이트) + **attack-path 상관규칙 R1~R5**. **4.6 신설**: terraform=레이어드, 폴더=컴포넌트, 공유편집 4파일, CI apply 자동화.
- **2026-06-30 / 진우 / 비용 최적화 + 설계 잔여 갭 해소** — Aurora→RDS t3.micro, NAT Instance+Gateway Endpoint, Prowler Azure 진입, Bedrock 모델 배정(Haiku/Sonnet), CIEM 분담 독립 행, Entra CIEM RAG 룰북.
- **2026-06-30 / 준형 / 공통 계약 4종 초안 확정 + 미확정 2건 닫음** — 4.4 합의 계약(OCSF-lite·엔진 입출력·attack-path·Evidence allowlist), 레포=모노레포 확정, attack-path=커스텀 엔진 확정.
- **2026-06-30 / 준형 / 작업 분담 표 통합 + 실명 반영** — 트랙1·2 → 준형·진우, 상시 협의 문서화.
- **2026-06-30 / 준형 / 작업 분담 균형안 도입** — 영역 반반, 의존성 순서, 합의 인터페이스 2개, 시간 컷 우선순위 명시.
- **2026-06-30 / 준형 / Azure 역할을 데이터→신원(Entra ID) 중심으로 전면 전환** — 골든 시나리오 크로스클라우드 신원 탈취 경로로 교체, 설계서 3종·README 동기화.

---

## 1. 한 줄 요약

멀티클라우드(**AWS = 워크로드의 주인 / Azure = 신원의 주인(Entra ID)**) 환경의 설정(Posture)부터 워크로드·IaC 코드까지 **code-to-cloud 보안 위험을 점검·통합·상관분석**하고, 그 위에 **에이전틱 AI(Bedrock 멀티에이전트 + RAG)**로 발견 항목을 설명·우선순위화·자동 개선하는 **CNAPP형 보안 플랫폼**. (데이터/회원 PII는 AWS S3 전용 — Azure에는 데이터를 두지 않는다.)

---

## 2. 핵심 키워드

- **Multi-Cloud** — AWS(워크로드의 주인) + Azure(신원의 주인, Entra ID). *각 클라우드 장점대로 — 컨테이너 워크로드는 AWS, Microsoft 생태계 신원은 Azure.* 흩어진 보안 상태를 OCSF로 정규화해 단일 뷰로 통합하고, **AWS 워크로드 침해가 Azure 신원(Entra) 장악으로 번지는 크로스클라우드 attack-path**까지 추적. (데이터는 AWS S3 전용, 중복 저장은 명분이 약해 Azure는 신원만.)
- **CNAPP** — CSPM·CIEM·취약점·KSPM·데이터(DSPM 맛)·attack-path 6기둥. CSPM을 넓히지 않고 **워크로드(코드 방향)로 깊게** 심화. SOC(실시간 위협탐지/대응)는 범위 밖(확장 훅만).
- **Agentic** — 챗봇이 아니라 에이전트가 능동적으로 일한다. **챗봇 탈출의 단일 기준 = LLM이 read-only API를 스스로 호출해 증거를 모으는가(tool use).** Orchestrator → Triage → Hypothesis → Evidence → Reasoning 루프(가설→증거→판정).

---

## 3. 핵심 설계 결정 (요약) ✅

상세·근거는 설계서 11번. 가장 자주 부딪히는 결정만 추림:

아래 표는 각 설계 결정과 그 요점을 정리한 것이다.

| 결정 | 요점 |
|---|---|
| **단일 계정 / 단일 리전(서울)** | Organizations·Identity Center·Control Tower **절대 안 켬**(무료 크레딧 소멸 트리거). CloudTrail/Config는 전 리전 수집. |
| **키 없는 인증** | CI/CD는 GitHub OIDC→IAM Role, 파드는 IRSA/Pod Identity. 장기 자격증명 미사용. |
| **EKS + ArgoCD GitOps** | 워크로드 운영·배포의 핵심 축. |
| **앱 2개** | ① 취약 타깃 앱(findings 소스) ② 관제 앱(HALO의 NOVA 대응, 얼굴). **둘은 직접 통신 안 함 — agentless.** |
| **취약점은 IaC에 심음** | 앱 코드 버그가 아니라 인프라/설정 결함. 기능 최소, 결함 다양성 최대. |
| **Bedrock + 수동 RAG** | SageMaker 미사용. 벡터DB = **pgvector(RDS/Aurora PostgreSQL)** 확정(코퍼스 작아 OpenSearch는 오버스펙). |
| **앱 SSO = Cognito 허브** | Entra ID(IdP) ─SAML→ Cognito ─OIDC→ ALB(authenticate-oidc). 워크포스 SSO 크레딧 회피. |
| **Azure = 신원(Entra ID) 중심** | 점검 핵심은 **Entra CIEM**(과도권한 앱 등록·위험한 consent·권한상승) + **Defender for Cloud**(리소스 secure score, 멀티클라우드 통합 뷰). Security Hub는 AWS 전용, Prowler로 멀티클라우드 병행. **Azure에 데이터는 두지 않음**(Defender 데이터 탐지 미사용). |
| **데이터는 AWS S3 전용 / Macie도 AWS 전용** | 회원 PII는 AWS S3에만 보관, 데이터 탐지(DSPM 맛)는 **Macie(AWS S3 전용)**. Azure는 데이터 저장소가 아니라 신원의 주인. |
| **골든 시나리오 = 크로스클라우드 신원 탈취** | product 취약 이미지 침투 → order 과도 IRSA + **평문 시크릿의 Azure 자격증명** → member 공개 S3로 AWS PII 탈취 → 탈취 자격증명으로 **Azure Entra ID 과도권한 앱/계정 장악**(디렉터리 전체 통제권). MVP는 분석·시각화 수준, 실제 횡단 동작은 보너스. |
| **Read-only first + HITL** | 에이전트는 기본 조회만. 변경(remediation)은 분리된 승인 경로(Step Functions) + 불변 감사로그(S3 Object Lock). |

**연결 구조(꼭 기억):** 타깃 앱은 AWS/Azure에 *배포*만 됨 → 스캐너가 계정을 **read-only로 스캔** → findings → EventBridge→SQS→Lambda → OCSF 정규화 → pgvector/엔진 → 관제 앱이 findings 저장소를 **읽어서** 표시. 타깃 앱↔관제 앱 직접 API 없음.

---

## 4. 폴더 구조 🏗️

```
cnapp-agentic/
├── CLAUDE.md                 # 작업 기준 + 협업 규칙 + 변경 로그
├── README.md
├── troubleshooting.md        # 작업 로그 (트러블슈팅 + 진행, [영역] 태그 한 줄씩)
├── contracts/                # ★공유 이음새 계약(4.4): *.json 스키마 + mock-findings.json (코딩 시 생성)
├── docs/                     # ★ 설계 SSOT (변경 시 반드시 여기 먼저 반영)
│   ├── project-draft.md      #   메인 설계서 (방향·범위·계약 4.4·구조 4.6·로드맵)
│   ├── target-app-design.md  #   타깃 앱 상세 (결함 목록·골든 attack-path)
│   ├── console-app-design.md #   관제 앱 상세 (화면·백엔드·RBAC·RAG 매핑)
│   └── manual-infra.md       #   수동 관리 리소스 현황 (계정·부트스트랩·Azure/Entra)
├── apps/
│   ├── target/               # 취약 타깃 앱 (product/order/member). 코드만
│   └── console/              # 관제 앱 (React). 코드만
├── scanners/                 # cspm(준형) / workload(진우). 코드만
├── pipeline/                 # ingest(준형) / normalize(진우). 코드만
├── engine/                   # core(공유·예외) / evidence(준형: triage·evidence) / reasoning(진우: hypothesis·reasoning)
├── rag/                      # corpus(준형) / retrieval(진우). 코드만
├── attackpath/               # model(준형) / correlation(진우). 코드만
└── infra/                    # Terraform — 레이어드(4.6). apply는 여기서만
    ├── shared/               #   기반(준형 최초 apply): VPC·EKS·OIDC·RDS pgvector·Bedrock·ECR
    ├── target/               #   취약 워크로드+의도적 결함(준형, 휘발성·격리)
    ├── console/              #   ALB·Cognito·console Lambda·SFn·CloudFront(진우)
    └── {scanners,pipeline,engine,…}/  # 영역별 terraform(영역 주인이 apply)
```

> **레포 = 모노레포 확정**(설계서 24번). 배포는 폴더별 분리(target=EKS, console=S3+Lambda). **terraform = 레이어드(project-draft 4.6)**: `infra/shared`(기반, 준형 최초 apply) → `infra/<영역>`(영역 주인이 apply, 쪼개기 영역 단위까지). 컴포넌트 폴더(scanners·pipeline·engine·rag·attackpath)는 코드만. **폴더는 컴포넌트로 나눔(사람 이름 폴더 금지)** — 단 하위는 **소유자별 2개**(a=준형·b=진우), **개수 최소화**(공유 코드만 예외 폴더). 세부는 파일로 구분. 소유표·이음새는 4.6. 공유편집 4파일=`contracts/`·`engine/core/`·`docs/`·`CLAUDE.md`. 코딩 시 공통 계약은 `contracts/*.json`(4.4 초안 졸업). 구조를 바꿀 땐 docs에 먼저 반영.

---

## 5. 작업 분담 (균형안 — 효율용 트랙)

> **원칙:** 일을 나누되 **둘 다 상대 영역까지 완전히 이해**한다. 각 영역을 반반 갈라 양쪽이 핵심을 다 만진다. 상세·의존성·인터페이스는 설계서 4번이 SSOT.
> ⚠️ **이 분담은 상시 협의로 계속 조정되는 살아있는 문서.** 변경 시 이 표와 설계서 4번을 **함께** 갱신한다.

| 영역 | 준형 | 진우 | 상태 |
|---|---|---|---|
| 앱 | **타깃 앱(결함 심기) + 관제 앱(대시보드·시각화)** | — (앱 2개 모두 준형 전담) | 확정 |
| 토대 | CI/CD·Shift-Left·**공유인프라 주도** | 모니터링·관제·추적(Grafana·CloudTrail) | 확정 |
| 스캐너-CSPM | CSPM(Config·Prowler·Security Hub·**Macie(AWS S3)**) | 워크로드(Inspector·Trivy·kube-bench·**Defender(Azure)**) | 확정 |
| 스캐너-CIEM | IAM Access Analyzer(AWS) | Entra ID(Azure — **Prowler entra_id_\* 체크**) | 확정 |
| 수집·정규화 | 수집부(EventBridge→SQS) | 정규화부(Lambda→OCSF) | 확정 |
| 엔진(Bedrock) | **Evidence(tool use)**·Triage | Hypothesis·**Reasoning**·Orchestrator | 확정 |
| RAG | 코퍼스·임베딩·pgvector 적재 | 검색·LLM 답변 생성 | 확정 |
| attack-path | 그래프 데이터 모델 | 상관 로직·내러티브 | 확정 |

> **전 영역 확정(진우 검증 완료).** 단 살아있는 분담 — 바뀌면 이 표와 설계서 4.1을 함께 갱신.

- **의존성(병목):** 0 공유인프라(준형 최우선) → 1 앱·모니터링 ∥ → 2 스캐너 ∥ → 3 수집→정규화 → 4 RAG ∥ → 5 엔진(Evidence∥Reasoning) → 6 출력 ∥ → 7 데모 합류.
- **공통 계약 7종 + 정규화 규칙 3종 확정(project-draft 4.4·4.4.1):** 계약 ① OCSF-lite 스키마(`resource_id`·`dedup_key`·`ai_status`) ② 엔진 입출력 ③ attack-path 그래프 JSON ④ Evidence 툴 allowlist ⑤ 수집 봉투 ⑥ 임베딩 모델+rag_chunk ⑦ 엔진 case 핸드오프(트리아지 게이트) + **상관규칙 R1~R5**. 정규화 규칙 **(a) `resource_id` 캐논 (b) INTERNAL `control_id` 카탈로그 (c) remediated 스코프(source별)**. `contracts/*.json` + `mock-findings.json`(R1~R5 체이닝) + `control-catalog.json`으로 졸업 → 직렬 의존 끊고 병렬.
- **시간 컷 우선순위:** 엔진 능동조사(1) > attack-path 상관(2) > 스캐너·수집·RAG(3) > 관제앱·CI/CD·포장(4). **"AI가 스스로 증거 모아 공격경로 판단하는 한 장면"** 사수.

**공유 자산(양쪽 함께):** 수집 파이프라인(EventBridge→SQS→Lambda, OCSF 정규화), 에이전틱 엔진 코어(`engine/`), 인프라 골격(`infra/shared/`), 관제 대시보드(`apps/console/`).

---

## 6. 협업 규칙 🔒

1. **작업 시작 전 `git pull`** — 항상 최신 main을 받고 시작. 충돌 줄이기.
2. **작업 후 `commit` + `push`** — 의미 단위로 커밋하고 바로 push해 상대가 받을 수 있게. 커밋 메시지는 `타입: 내용`(예: `feat: ...`, `docs: ...`, `infra: ...`).
3. **설계 변경은 docs에 먼저 반영** — 방향·범위·구조·결정이 바뀌면 [docs/](docs/)의 해당 설계 문서(project-draft / target-app-design / console-app-design)를 **먼저** 업데이트하고, 영향이 있으면 본 CLAUDE.md도 갱신. 코드/문서 불일치를 남기지 않는다.
4. **무료 티어 가드레일 준수** — Organizations/Identity Center/Control Tower 금지. 종량제 서비스(Config·Security Hub·Inspector·Macie·Defender)는 데모 기간만 켜고 `destroy`. Budgets 알림 유지.
5. **보안 기본** — 장기 키 커밋 금지(OIDC/IRSA 사용), 시크릿은 Secrets Manager+KMS. 에이전트는 read-only first, 변경은 HITL 승인 경로로만.

---

## 7. 앞으로의 작업 기준 🗓️

- **모든 작업은 `docs/`와 이 `CLAUDE.md`를 기준으로 진행한다.** 새 기능·결정·구조 변경은 먼저 설계 문서와 정합성을 확인하고, 어긋나면 문서를 갱신한 뒤 코드를 작성한다.
- 우선순위 컷라인(설계서 21번): **① 절대사수** = CSPM 본체 + RAG 설명 + 대시보드 + Azure 통합 + Shift-Left + KSPM, **② 보너스** = 공급망 서명·attack-path 정교화·ISMS-P 리포트, **③ 확장** = CWPP 런타임·SOC.
- 미확정 항목(설계서 24번)은 결정될 때마다 docs에 반영하고 여기 요약을 갱신한다.

### 7.1 현황 + 다음 할 일 (Next Up — ★진행 관리 단일 지점. 작업 후 여기부터 갱신)

> **이 절만 보면 "지금 어디까지 / 다음 뭐"가 나온다.** 큰 그림 현황은 [README 구현 현황](../README.md) 표, 상세 작업 로그는 [troubleshooting.md](../troubleshooting.md).

**현황 + 다음 (사람별 · 2026-07-01):**

*준형*
- ✅ 한 것: 관제 앱 **8화면 목업 동작** · 타깃 앱 **member 실행 + shop 포털** · **엔진 Evidence·Triage 능동조사(목업, `python -m engine.run_demo`)** · 공통 계약(14 control·목업·CI) · `infra/shared`·`infra/target` 스캐폴드(apply 전)
- ▶ 다음: attack-path 그래프 모델(R1~R5 상관은 진우) → console-backend(TS Lambda) → *(실검증)* 엔진 `RealToolExecutor`로 실 read-only API tool-use

*진우*
- ✅ 한 것: TF state 버킷 · Cognito SSO 설계(authenticate-cognito·그룹 클레임) · 2-pass 트리거 이벤트
- 🔄 지금: Azure/Entra 데모 테넌트(M365) 생성
- ▶ 다음: App Registration(SSO)+그룹 → 결함/스캔 SP (manual-infra §3 순서) · 워크로드 스캐너 · 정규화부 · 엔진 Reasoning

*공통 미완:* 스캐너 실행 · 수집/정규화 · RAG · infra apply(비용)

**진행 원칙 (하이브리드 — free credit 감안, 2026-07-01 확정):**
- **빌드 순서**는 인프라 먼저가 자연스러움(§5 의존성). 단 **목업 우선**으로 논리(엔진·콘솔·상관)를 인프라 없이 **병렬로 빠르게** 만든다.
- **리스크 큰 실검증은 실클라우드로 조기에** — 특히 **엔진 실 read-only API tool-use**(목업으론 완전 검증 불가)와 **스캐너 1개→실 finding 1개** 경로. 단 `apply → 테스트 → destroy` **사이클**로(상시 켜두기 X — 취약 타깃 방치·크레딧 소모 방지).
- **시간 부족 시 사수** = 엔진 능동조사 1경로(Evidence tool-use real) + 골든 attack-path 1경로 시각화(§5 시간 컷 우선순위).
