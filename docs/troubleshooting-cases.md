# 트러블슈팅 로그 — 멀티클라우드 CNAPP 보안 플랫폼

2인 협업 프로젝트에서 **내가 직접 원인을 찾아 고친 문제**를 기록한다. 협업자가 주도한 관측·정규화·상관 영역의 문제는 뺐다. 형식: `날짜 · [영역]` — 증상 / 원인 / 조치 / 느낀점. 최신순.

## 대표 사례

중요하게 생각한 것들. 상세는 아래 로그에.

- **비용 게이트를 뚫고 Bedrock 호출 5배 폭증** (07-24) — 비용 막으라고 만든 게이트가 노이즈에 뚫려 있었다. batch_size는 배치가 아니다.
- **terraform plan 지뢰 3건 — 그냥 apply만 해도 데모가 무너짐** (07-24) — 안전한 기본값이 오히려 취약 데모를 되돌렸다.
- **풀 destroy가 shared에서 멈춤 — 고아 pod ENI가 SG를 붙잡음** (07-24) — 안전훅의 "노드 종료=ENI 해제" 가정이 죽은 컴포넌트에 의존해 깨졌다.
- **"실 지식베이스로 검색"이 사실이 아니었다** (07-21) — RAG 청크가 0개인 채로 근거 없이 답하고 있었다.
- **X-Ray로 잡은 normalize 2-pass 조용한 실패** (07-08) — 관측 코드 한 줄이 실시간 상관분석 트리거를 매번 죽이고 있었다.
- **destroy→재apply가 팀원 작업을 조용히 덮어씀** (07-08) — terraform 초록불은 "최신"이 아니라 "내 코드 기준 성공"일 뿐.
- **deploy.ps1이 스크립트 안에서만 간헐 실패** (07-03) — PS5.1이 UTF-8 한글 주석을 cp949로 오독해 다음 실행문을 삼켰다.
- **apply 직전 객관 리뷰로 잡은 apply-blocker 3건** (07-02) — EKS 버전 하나가 컨트롤플레인 비용을 6배로 만들 뻔했다.

---

## 전체 로그

### 2026-07-24 · [infra] — 풀 destroy가 shared에서 멈춤 (고아 pod ENI가 SG를 붙잡음)
- **증상** — 6레이어 destroy 중 shared만 `DeleteSecurityGroup ... DependencyViolation`으로 실패(EKS·RDS는 이미 삭제 완료였는데도).
- **원인** — 고아 스팟노드는 종료됐지만 그 VPC-CNI pod ENI(`aws-K8S-<id>`)가, CNI 컨트롤러가 클러스터와 함께 죽어 GC되지 못하고 `available`로 노드 SG를 계속 참조. 훅이 "노드 종료=ENI 해제"라고 가정했는데 실제 해제는 이미 죽은 컴포넌트(CNI 컨트롤러)에 의존.
- **조치** — `available` ENI를 삭제하고 destroy 재개. 훅에 "종료 노드별 available pod ENI 삭제" 로직 추가(in-use는 안 건드림).
- **느낀점** — 안전훅이 "A하면 B가 따라온다"고 가정할 때, B가 종료 순서상 이미 죽은 컴포넌트에 의존하면 그 가정은 조용히 깨진다.

### 2026-07-24 · [pipeline] — Security Hub 활성 직후 Bedrock 호출 5배 폭증
- **증상** — 서비스를 켠 뒤 Bedrock 호출이 시간당 98 → 528회, orchestrator 2시간에 1053회.
- **원인** — ① SQS `batch_size=10`인데 `maximum_batching_window=0`이라 메시지 도착 즉시 1건짜리 배치로 Lambda 기동(batch_size는 상한일 뿐 배치가 아님) ② 전부 suppressed인 배치도 후속 이벤트를 무조건 발행 ③ Security Hub가 같은 finding을 재평가마다 재발행하는데 재유입이 게이트를 그대로 통과.
- **조치** — 배칭 창 30초 + actionable일 때만 발행 + upsert `RETURNING (xmax=0)`으로 "처음 들어온 open"일 때만 기동. → 5분당 60 → 1회.
- **느낀점** — "무엇을 조사할지"(게이트)와 "언제 다시 처리할지"(멱등성)는 별개 축이다. 둘 다 없으면 외부 소스 재발행마다 비용이 샌다.

### 2026-07-24 · [pipeline] — 트리아지 비용 게이트가 노이즈에 뚫려 있었다
- **증상** — findings 387건 중 314건(81%)이 미매핑 UNKNOWN, Secure Score 10/100.
- **원인** — 미매핑 finding이 심각도 없이 open으로 쌓여, 그중 Critical·High 88건이 `severity_id≤2` 게이트를 통과해 Bedrock 조사를 유발. 손으로 지워도 Prowler cron이 매일 재생성.
- **조치** — normalizer `_make_finding`에서 미매핑 FAIL을 open이 아니라 suppressed로 생성(6개 파서 일괄). 배포 후 findings가 387→412로 늘어도 open은 24로 그대로.
- **느낀점** — 비용을 막으라고 만든 게이트가 정작 노이즈에 열려 있었다. 저볼륨일 땐 안 보이다 실 스캐너를 붙이자 드러났다.

### 2026-07-24 · [infra] — terraform plan 6레이어 전수조사, apply만 해도 데모가 무너지는 지뢰 3건
- **증상** — 보안 서비스를 켠 뒤 plan을 돌리니 라이브를 되돌리려는 drift가 잡힘.
- **원인** — 변수 기본값이 안전(false)한데 라이브는 의도적으로 위험한 쪽이라 plan이 그 차이를 고치려 듦. ① `enable_s3_public`(적용 시 attack-path 3→1) ② `enable_overpriv_irsa`(hero 경로 Critical 노드 축소) ③ Cognito가 자동 파생하는 SAML 3키를 plan이 매번 null로 지움(SSO 파괴).
- **조치** — ①② deploy.ps1 레이어별 기본 변수 맵, ③ `lifecycle ignore_changes`. → 6레이어 전부 No changes.
- **느낀점** — "위험한 값을 안전하게 기본값으로 두는" 관행이, 의도적으로 취약해야 하는 데모 환경에선 정반대로 작동한다.

### 2026-07-24 · [infra] — "보안 서비스 4종 계정 제약" 오진을 뒤집음
- **증상** — Security Hub·Macie·Inspector·GuardDuty 4종이 18일간 `SubscriptionRequiredException`으로 막혀 "계정 하자"로 결론내고 범위 제외해뒀음.
- **원인** — CLI로만 보던 걸 웹 콘솔로 열자 답이 있었음: 2025-07 신설 AWS 무료 플랜이 "크레딧을 소진할 수 있는 서비스" 접근을 정책으로 차단(계정 하자 아님).
- **조치** — 업그레이드해도 크레딧이 이월됨을 문서로 확인 후 Paid 전환 → 에러가 `InvalidAccess`(미활성)로 바뀌는 걸로 검증, 6종 활성화.
- **느낀점** — CLI 에러 코드만 보고 계정 하자로 단정하지 말 것. 콘솔 안내문이 CLI가 못 주는 원인을 줬다. (07-06의 내 최초 진단을 뒤집은 것)

### 2026-07-24 · [pipeline] — 같은 리소스인데 중복 finding으로 남던 원인 (dedup_key가 옛 가짜명)
- **증상** — member-pii-prod S3, github-ci IAM 건이 각각 2건씩 중복.
- **원인** — 07-10에 골든 finding의 `resource_id`만 실명으로 바꾸고 `dedup_key`는 설계 당시 가짜명 그대로 둬, 계약(`resource_id|control_id`)이 깨져 실스캔과 영영 안 합쳐짐.
- **조치** — UNIQUE 제약 때문에 중복 sources를 골든에 흡수 → 버릴 행 suppressed → 골든 키 교정 순서로(삭제 대신 억제로 FK 안전).
- **느낀점** — 실명으로 바꿀 땐 파생 키(dedup_key)까지 함께 바꿔야 정합이 유지된다.

### 2026-07-24 · [scanners] — Macie가 합성 PII를 0건 탐지
- **증상** — DSPM 실증용 Macie 분류가 COMPLETE인데 findings 0건.
- **원인** — ① 관리형 데이터 식별자에 한국 주민번호 항목이 아예 없음 ② seeder RRN 200개 중 체크섬 유효한 게 18개뿐 ③ 이메일이 전부 예약 테스트 도메인(example.com)이라 탐지 제외.
- **조치** — 정규식 기반 커스텀 데이터 식별자(cnapp-korea-rrn)를 직접 정의해 재스캔 → RRN 200건 탐지.
- **느낀점** — 우회가 아니라 정공법. 조직 고유 민감정보 패턴을 직접 정의하는 게 DSPM의 핵심 기능이다.

### 2026-07-24 · [infra] — 타임아웃으로 죽은 terraform plan이 state lock을 남김
- **증상** — 백그라운드 러너의 2분 타임아웃으로 plan이 강제 종료되며 S3 backend에 lock 잔존 → 이후 모든 plan 실패.
- **원인** — 긴 terraform 명령을 타임아웃 있는 러너로 돌리면 강제 종료 시 lock이 안 풀림.
- **조치** — lock 생성 시각·프로세스 목록으로 자기 죽은 프로세스임을 확인 후 force-unlock.
- **느낀점** — 긴 plan/apply는 타임아웃 러너 말고 백그라운드로.

### 2026-07-21 · [engine·rag] — "실 지식베이스로 검색"이 사실이 아니었다
- **증상** — 라이브 `/api/system`이 `rag:{chunks:0}`. `/chat`이 근거 없이 답하고, "pgvector 검색" 표시가 사실이 아닌 상태.
- **원인** — 적재 코드는 있으나 레포 전체에서 호출부가 0건이라, 재apply 때 rag_chunks가 날아간 뒤 아무도 복구 못 함. 게다가 orchestrator에 `rag` import 자체가 없어 `rag_refs`가 항상 `[]`, 트리아지 통과 19건 중 13건이 미조사.
- **조치** — `load_live.py` 신설로 적재 절차 코드화(청크 0→26) + orchestrator RAG 배선 + 잔여 escalated 배치 처리(미조사 13→0).
- **느낀점** — 화면에 "라이브"라 적혀 있어도 실제로 라이브가 아닐 수 있다. 재apply마다 죽는 자산은 복구 절차를 코드로 남겨야 한다.

### 2026-07-21 · [engine] — LLM에게 '호출 불가능한 툴'을 주던 버그
- **증상** — 플래너가 허용목록을 그대로 tool enum으로 넘겨, LLM이 실행 핸들러도 없는 API 3종을 "호출할 것"으로 고를 수 있었음 → 고르면 `NotImplementedError`로 턴만 낭비(광역 except에 먹혀 조용히).
- **원인** — allowlist(허용 경계)와 실제 실행 가능한 API를 구분하지 않고 enum에 그대로 사용.
- **조치** — `executable_apis()`를 enum으로 분리(enum ⊆ allowlist라 경계는 안 넓어짐).
- **느낀점** — LLM에게 주는 선택지(enum)와 정책 경계(allowlist)는 별개다. 경계 목록을 곧장 선택지로 주면 못 쓰는 걸 고른다.

### 2026-07-13 · [infra·apps-console] — 풀사이클 재apply마다 Cognito Pool ID가 재발급돼 SSO가 깨짐
- **증상** — 인프라를 fresh apply(재생성)한 뒤 기존 로그인이 안 됨. SPA 로그인 버튼이 옛 Pool을 가리킴.
- **원인** — destroy 후 재apply는 Cognito User Pool을 새로 만들어 Pool ID가 매번 바뀜(예: `ap-northeast-2_a4N8fqDUE`). SPA에 주입된 client/pool 참조가 어긋나고, Entra SAML 식별자(`urn:amazon:cognito:sp:<PoolId>`)도 옛 값이라 페더레이션이 끊김.
- **조치** — 새 Pool ID로 SPA 재빌드·재배포 + Entra 앱 SAML 식별자 수동 교체. 이 재연결 절차를 재apply 런북(manual-infra)에 고정.
- **느낀점** — apply→destroy를 반복하는 프로젝트에선 "재생성 때마다 바뀌는 식별자(Pool ID)"가 외부 연동(SSO)을 매번 깬다. 재현 가능성과 외부 신뢰관계는 상충하니 재연결 절차를 런북으로 남겨야 한다.

### 2026-07-13 · [ci] — 헬스 캔어리가 계획된 destroy 중에 오탐 알림
- **증상** — 인프라를 의도적으로 내리는 동안 live-health-canary(20분마다 SPA·API를 실제 호출)가 "서비스 다운"으로 Teams에 알람을 쏨.
- **원인** — 사용자 관점 헬스 체크는 "계획된 destroy"와 "실제 장애"를 구분하지 못한다.
- **조치** — destroy 전 캔어리 스케줄을 일시 정지(유지보수 창 동안 억제).
- **느낀점** — 외형 프로빙 알림은 유지보수 창을 모른다. 계획된 다운타임엔 알림을 끄는 절차가 함께 있어야 한다.

### 2026-07-13 · [apps-console] — 조치를 승인해도 화면이 안 바뀌어 "먹혔는지" 안 보임
- **증상** — 데모에서 조치를 승인해도 대시보드 점수·attack-path가 그대로라, 조치가 실제로 적용됐는지 화면상 알 수 없었다.
- **원인** — 조치는 백엔드(Step Functions)에서 실제로 실행돼 finding이 remediated로 바뀌는데, 콘솔이 그 변화를 자동으로 다시 불러오지 않아 수동 새로고침 전까진 옛 상태를 계속 보여줬다.
- **조치** — 조치 성공 후 findings·점수·경로 쿼리를 무효화해 자동 갱신 + 바뀐 수치에 델타(증감) 강조.
- **느낀점** — 백엔드가 맞게 동작해도 화면이 그 변화를 안 비추면 "동작 안 하는 것처럼" 보인다. 상태 변경 액션은 결과를 눈에 보이게 되먹여야 데모·운영 둘 다 신뢰가 선다.

### 2026-07-10 · [attackpath] — 멀티경로(1→3) 전환 라이브 배포 중 실버그 3건
- **증상** — 리팩터 후 그래프 노드 라벨이 리소스와 불일치(재실행마다 다른 결과), 조치 후에도 콘솔이 옛 경로를 표시.
- **원인** — ① `_first(control_id)`가 ORDER BY 없는 RDS 조회라 엉뚱한 행을 집음(비결정성) ② correlation이 없어진 경로를 DELETE 안 해 stale row 잔존 + backfill이 방금 삭제된 id를 되써 FK 위반.
- **조치** — 명시 지목 + `_delete_stale_paths`(`::uuid[]` 캐스트) + backfill이 경로 밖 finding을 clear.
- **느낀점** — 무순서 DB 조회에 그래프 노드를 매핑하면 비결정성이 그래프를 오염시킨다.

### 2026-07-08 · [apps-console] — 조치 승인 버튼이 스텁이라 "눌러도 아무것도 안 됨"
- **증상** — approver로 승인해도 프론트 로컬 배지만 뜨고 새로고침하면 사라짐.
- **원인** — 프론트·IAM·Step Functions·remediation은 다 있었는데 백엔드 `/approve` 핸들러가 `{ok:true}` 껍데기(MVP 때 미뤄둔 것).
- **조치** — `decideRemediation()` 신설(finding→control_id→INSERT→SFn StartExecution). 드리프트 없는 조치만 데모용으로 선별. Lambda invoke로 SFn SUCCEEDED·open 20→19 검증.
- **느낀점** — 프론트+IAM+실행엔진이 다 돼있어도 중간 백엔드 핸들러 한 줄이 스텁이면 기능 전체가 죽는다.

### 2026-07-08 · [apps-console] — 만료 토큰으로도 approver로 보이고 승인 시 정체불명 실패
- **증상** — 만료된 ID 토큰으로도 approver로 표시, 승인 클릭 시 `res.json()`이 `'<'`에서 파싱 실패.
- **원인** — ① 프론트가 토큰 '존재'만 확인하고 `exp`를 무시(백엔드는 검증해 viewer로 강등하는데 프론트만 몰라 불일치) ② 만료 승인→백엔드 403→CloudFront `custom_error_response`(403→200 index.html)가 403을 200 HTML로 가림.
- **조치** — `isTokenExpired()`(exp vs now+skew) + 세션 만료 감지 + 200이어도 content-type이 JSON 아니면 401로 던짐.
- **느낀점** — SPA+API를 한 CloudFront에 섞으면 SPA용 403→200 리라이트가 API 에러를 가린다. 프론트는 status뿐 아니라 content-type도, 만료도 exp를 직접 봐야 한다.

### 2026-07-08 · [security] — WAF 검증 중 "차단됐는데 curl은 200" 착시 (WAF는 정상)
- **증상** — XSS 페이로드를 쐈는데 curl이 200 반환 → "WAF가 안 막나?" 의심.
- **원인** — WAF는 실제로 차단하고 있었음. 200의 정체는 CloudFront SPA용 `custom_error_response`(403→200 index.html)가 차단 응답까지 index.html로 바꾼 것(Content-Type: 정상=json vs 차단=html).
- **조치** — 차단 판단을 HTTP status 대신 CloudWatch WAF 지표·응답 Content-Type으로.
- **느낀점** — SPA용 에러 리라이트가 있는 CloudFront에선 HTTP status로 보안 동작을 판단하면 안 된다.

### 2026-07-08 · [pipeline] — X-Ray 트레이스맵에서 발견한 normalize 2-pass 트리거 조용한 실패
- **증상** — X-Ray에 normalize·correlation·orchestrator가 빨간 에러 아이콘.
- **원인** — 실제 원인은 normalize 하나 — 배치완료 이벤트 발행부가 Lambda 최상위(읽기전용 FacadeSegment)에 annotation을 직접 써 `FacadeSegmentMutationException`. 이 예외가 correlation을 깨우는 2-pass 실시간 트리거 직전에서 죽어, findings는 저장되는데 상관분석 트리거가 매번 조용히 실패(DLQ 0건이라 티 안 남).
- **조치** — `begin_subsegment()`로 서브세그먼트를 열어 annotate.
- **느낀점** — Lambda 최상위 세그먼트는 SDK 소유라 직접 mutate 금지. 관측 코드 한 줄이 핵심 파이프라인을 조용히 끊을 수 있다.

### 2026-07-08 · [apps-console] — 감사로그 페이지가 실데이터에서만 크래시
- **증상** — 실데이터에서만 감사로그 전체 페이지 백지(`undefined 'cls'`).
- **원인** — 백엔드가 내보내는 action 값(`apply`/`request`)이 프론트 타입·메타에 없어 TypeError. mock 픽스처엔 이 값이 없어 로컬 빌드로는 안 걸림.
- **조치** — 타입·메타에 값 추가 + 미지 값 방어 fallback.
- **느낀점** — mock→real 전환 시 필드 유무뿐 아니라 "값의 종류(enum)"까지 실 DB가 낼 수 있는 값 전체와 대조해야 한다.

### 2026-07-08 · [infra] — destroy 중 세션 종료로 backend가 절반만 destroy된 채 멈춤
- **증상** — SG 삭제 중 끊김, 재개 시 state lock 에러 + "log group already exists".
- **원인** — 백그라운드 실행이 세션 프로세스에 종속돼 세션 종료 시 terraform도 죽음. SG는 삭제된 Lambda의 Hyperplane ENI가 붙잡던 것, lock은 죽은 프로세스가 미해제, 로그그룹은 이전 destroy 잔존.
- **조치** — 로그 대신 `aws describe-*`로 실제 상태 확인 → available ENI 삭제 → force-unlock → 로그그룹은 `terraform import`로 편입.
- **느낀점** — 긴 terraform을 백그라운드로 돌릴 땐 세션 끊김을 염두에 두고, 재개 시 로그가 아니라 aws 커맨드로 실제 상태부터 확인.

### 2026-07-08 · [infra] — destroy→재apply 사이클이 팀원 작업을 조용히 지울 뻔함
- **증상** — 재apply 후 에러 0인데 협업자의 X-Ray 트레이싱(5개 Lambda)·Prowler 파이프라인이 사라짐.
- **원인** — 로컬 구버전 코드로 backend를 재생성해, 그 사이 push+apply된 것이 구버전으로 조용히 덮어써짐(라이브 Lambda `TracingConfig.Mode=PassThrough`를 직접 조회하고서야 발견).
- **조치** — `git pull --rebase`로 통합 후 재빌드·재apply → 5개 Lambda `Active` 재확인. destroy·재apply 전 `git fetch`+`git log HEAD..origin/main` 규칙화.
- **느낀점** — 멀티오너 terraform에선 "조용히 구버전으로 덮어써 아무도 못 알아채는 것"이 destroy보다 위험하다.

### 2026-07-08 · [apps-console] — Cognito SAML 3키가 plan에서 null로 지워지는 diff
- **증상** — apply 전 plan에서 인증서·SSO/SLO URL이 null로 지워지는 diff(과거 SAML 재설정 사고 이력).
- **원인** — 리소스가 `MetadataURL` 하나만 선언 — 나머지 3키는 Cognito가 메타데이터를 읽어 매번 자동 파생하는 값이라 HCL 미관리, 매 plan마다 코스메틱 diff.
- **조치** — -target apply 후 `describe-identity-provider`(state 아닌 실 API)로 값이 살아있음 확인 → 정상 diff로 확정.
- **느낀점** — -target에 의도치 않은 리소스가 딸려 나오면 state 대신 실 AWS API로 라이브 값을 직접 확인.

### 2026-07-07 · [apps-console] — 실데이터 크래시 2건 (mock엔 안 나던 것)
- **증상** — ⓐ Finding 상세 전체 크래시 ⓑ Evidence 탭이 실모드에서 반쪽.
- **원인** — ⓐ 백엔드 실쿼리 `F_COLS`에 `sources` 누락 → 프론트 `f.sources.join()`이 `undefined.join()` ⓑ 실 case 쿼리가 `triage·hypotheses·evidence_meta·model_trace` 누락. mock엔 전 필드가 있어 안 터짐.
- **조치** — 실쿼리에 누락 컬럼 추가 + 프론트 방어적(`?.`·`??[]`).
- **느낀점** — mock=계약 JSON(전 필드) vs real=pgvector(선택 컬럼) 2경로라, 프론트 필드↔실쿼리 컬럼을 전수 대조해야 한다.

### 2026-07-07 · [apps-target] — member PII seeder가 기동 시 403 (IRSA 정상인데도)
- **증상** — IRSA 배선·정책 다 정상인데 seeder가 403 HeadObject.
- **원인** — ① 정책이 `s3:HeadObject`를 줬는데 그런 IAM 액션이 없음(HeadObject는 `s3:GetObject`로 인가) ② S3는 `ListBucket`이 없으면 없는 객체의 Head를 404 아닌 403으로 응답(존재 은닉).
- **조치** — `GetObject`로 교체 + `s3:ListBucket` 추가 → 적재 성공.
- **느낀점** — 'IRSA 됐는데 S3 403'이면 액션명이 실존 IAM 액션인지, 없는 객체 조회에 ListBucket이 필요한지 확인.

### 2026-07-07 · [infra] — destroy 중 shared가 2회 DependencyViolation (Karpenter 고아 노드)
- **증상** — shared destroy가 SG 삭제에서 두 번 실패.
- **원인** — karpenter destroy가 컨트롤러를 스팟 노드 회수보다 먼저 지워, 스팟 노드 1대가 잔존 → 그 pod ENI가 노드 SG를 붙잡아 15분 대기 후 실패.
- **조치** — in-use ENI 확인 → terminate → wait → shared destroy 재개. (07-24에 훅으로 코드화)
- **느낀점** — karpenter destroy 전 워크로드를 scale 0 하거나 Karpenter가 노드를 비우게 두고 지울 것.

### 2026-07-07 · [apps-console] — psql Job으로 RDS에 한글 seed 시 전부 깨짐
- **증상** — `PGCLIENTENCODING=UTF8`을 줘도 한글이 손상.
- **원인** — 파일→psql 인코딩 체인이 UTF-8 멀티바이트를 오독.
- **조치** — JSON 필드를 `\uXXXX` ASCII 이스케이프로 생성해 SQL을 순수 ASCII화 → jsonb 파싱 시 정상 한글 복원.
- **느낀점** — RDS에 한글을 psql Job으로 seed할 땐 파일 인코딩을 믿지 말고 `\uXXXX`로.

### 2026-07-06 · [scanners] — 실 kube-bench 스캔이 normalize로 안 들어옴 (3중 함정)
- **증상** — 스캔은 돌았는데 콘솔 건수 그대로.
- **원인** — ① PowerShell `>` 리다이렉트가 stdout JSON을 UTF-16 LE(BOM)로 저장 ② `aws lambda invoke` 백그라운드가 세션 teardown에 끊겨 응답 미작성 ③ 미매핑 PASS가 UNKNOWN-remediated로 collapse.
- **조치** — UTF-8 재저장 + 포그라운드 동기 invoke + normalizer에 "미매핑 && PASS면 finding 안 만듦" 규칙.
- **느낀점** — 라이브 결과는 invoke 출력이 아니라 실제 산출물(RDS/API count)로 확인.

### 2026-07-06 · [infra] — 보안 서비스 4종 enable이 SubscriptionRequiredException (최초 진단)
- **증상** — 4종 enable이 전부 "needs a subscription".
- **원인** — 처음엔 free tier 제약으로 오진 → 다 직접 enable 시도해 "이 보안서비스류만 구독 개시가 막힌 상태"로 확정(유료 서비스는 정상).
- **조치** — 실 CSPM은 구독 불필요한 Prowler로 우회.
- **느낀점** — describe/get의 SubscriptionRequired는 "아직 안 켜짐"일 뿐, enable을 직접 시도해야 진짜 제약인지 확정된다. (18일 뒤 진짜 원인이 신 무료 플랜임을 밝혀 이 결론을 뒤집음)

### 2026-07-06 · [apps-console] — 관제앱이 순백 화면 (코드가 아니라 배포 MIME)
- **증상** — curl은 200인데 브라우저는 순백, ErrorBoundary 폴백도 안 뜸.
- **원인** — 이 윈도 머신에서 `aws s3 sync/cp`가 `--content-type` 없이 올리면 `.js`를 `text/plain`으로 태깅 → 브라우저가 `<script type=module>`을 거부(terraform은 올바르게 넣는데 s3 sync가 덮어씀).
- **조치** — `aws s3 cp --content-type application/javascript` 재업로드 + 무효화. 진단은 playwright 헤드리스로 pageerror 캡처(curl은 200이라 안 보임).
- **느낀점** — 이 머신에선 SPA 배포를 terraform apply로 하거나 cp에 content-type을 명시.

### 2026-07-06 · [apps-console] — console-backend가 JWT를 서명검증 없이 디코드만 함 (플랫폼 취약점)
- **증상** — 위조 approver 토큰(`custom:groups`에 approver GUID)으로 조치 승인 권한 상승이 가능했음.
- **원인** — `auth.ts`가 Bearer JWT를 디코드만 하고 서명·iss·aud·exp를 검증하지 않음.
- **조치** — `aws-jwt-verify`(Cognito JWKS)로 검증 추가, 미설정/실패 시 fail-closed(viewer). 타깃앱 의도적 결함과 구분되는 '플랫폼' 취약점.
- **느낀점** — 자기 제품을 도그푸딩하면 진짜 익스플로잇 가능한 취약점이 나온다.

### 2026-07-06 · [apps-console] — `/api/chat`이 간헐 502(59ms 즉시)로 플래핑 (코드 아님)
- **증상** — 간헐 502, 즉시(59ms) 반환.
- **원인** — Lambda 로그에 START/END 자체가 없어 '요청이 Lambda에 안 닿음' 확인 → 그 시점 진행 중이던 노드그룹 교체(default→baseline)의 VPC/오리진 순간 블립.
- **조치** — 노드그룹 교체 완료 후 /chat 3/3 200 안정 확인.
- **느낀점** — 라이브 인프라 변경 중엔 데이터플레인 순간 502가 가능. 변경 후 재검증.

### 2026-07-06 · [apps-target] — product 파드 CrashLoopBackOff (`/bin/sh: [sleep,: command not found`)
- **증상** — product 파드만 크래시(member는 정상).
- **원인** — Dockerfile exec-form 함정 — `CMD ["sleep","infinity"]` 뒤 같은 줄 인라인 주석을 붙이면 JSON 파싱 실패→shell-form 폴백. member(주석 없음)와 대조로 확정.
- **조치** — 주석을 CMD 위 줄로 이동(근본수정) + 재빌드 전까진 매니페스트 command로 우회.
- **느낀점** — exec-form CMD 줄에는 인라인 주석 금지.

### 2026-07-06 · [apps-console] — 커스텀 도메인 콘솔이 실데이터를 못 부름 (mixed-content)
- **증상** — HTTPS 페이지가 데이터를 못 불러옴.
- **원인** — HTTPS 페이지가 HTTP ALB API를 직접 호출 → 브라우저 mixed-content 차단.
- **조치** — CloudFront에 `/api/*` → ALB 프록시 behavior 신설(뷰어엔 HTTPS·오리진엔 HTTP, 같은 오리진이라 CORS도 불필요).
- **느낀점** — SPA와 API를 한 오리진(CloudFront)으로 묶으면 mixed-content·CORS를 동시에 회피.

### 2026-07-06 · [infra] — deploy.ps1 비대화형 무한 행 (1시간 진척 0)
- **증상** — 백그라운드 apply가 1시간 진척 0(리소스 0 생성이라 비용은 0).
- **원인** — `-AutoApprove` 없으면 terraform apply가 승인 프롬프트에서 리다이렉트된 stdin을 기다려 영원히 블록(`-input=false`만으론 이 프롬프트 안 막힘).
- **조치** — deploy.ps1에 가드 — 비대화형인데 `-AutoApprove` 없으면 2초 만에 throw. + 킬한 프로세스의 stale lock force-unlock.
- **느낀점** — "옵션만 있고 실제 동작 조건은 따로"인 것들 — 승인 자동화는 명시적으로 강제해야 한다.

### 2026-07-06 · [infra] — ArgoCD 설치 실패 (CRD annotation "Too long: 262144 bytes")
- **증상** — `kubectl apply -f install.yaml`이 `applicationsets` CRD에서 실패.
- **원인** — client-side apply가 last-applied-config를 annotation에 넣는데 이 CRD가 한도 초과.
- **조치** — `kubectl apply --server-side --force-conflicts`.
- **느낀점** — 큰 CRD는 server-side apply. ArgoCD 표준 함정.

### 2026-07-06 · [rag] — `/chat` 500 (Sonnet Bedrock 액세스 미개방)
- **증상** — 엔진 Haiku는 되는데 RAG용 `/chat`만 500.
- **원인** — "Model access is denied ... aws-marketplace:Subscribe" — 관리자로 직접 호출해도 같은 에러 = 계정에 해당 모델 미구독(콘솔 수동 승인 필요).
- **조치** — RAG 모델을 열려있는 Haiku로 env 오버라이드 스왑(`CHAT_MODEL_ID`/`RAG_MODEL_ID`).
- **느낀점** — 모델별 액세스가 다르다. 모델 ID를 코드가 아닌 env로 두면 무코드 스왑이 가능하다.

### 2026-07-04 · [engine] — RealToolExecutor가 존재하지 않는 버킷에서 조사 전체 크래시
- **증상** — orchestrator 라이브 관통 중 investigate 전체가 죽음.
- **원인** — 실 Bedrock이 없는 버킷의 `s3:GetBucketAcl`을 골랐는데 핸들러가 `NoSuchBucket`을 안 잡고 예외를 그대로 던짐.
- **조치** — S3 핸들러에 `NoSuchBucket→중립결과` + 플래너에 광역 except(도구 예외를 error toolResult로 되돌려 조사 지속).
- **느낀점** — 에이전트가 스스로 도구를 고르므로 없는 리소스를 조회할 수 있다. 사람 조사자처럼 "없네, 다른 각도로" 하도록 강등 처리.

### 2026-07-04 · [apps-console] — ALB→console-backend 502 (Lambda는 정상)
- **증상** — 직접 invoke는 200인데 ALB만 502 지속.
- **원인** — 권한·타깃등록·헬스 다 정상 → 응답 포맷 의심. `statusDescription`이 `"200"`인데 ALB는 `"200 OK"` 형식을 요구, 안 맞으면 502.
- **조치** — 사유구 매핑으로 수정 → 전 엔드포인트 200.
- **느낀점** — 이전 세션이 이 502를 "스키마 미적용" 탓으로 오진했었음. 증상이 같아도 원인은 응답 포맷이었다.

### 2026-07-03 · [infra·ci] — deploy.ps1이 스크립트 안에서만·간헐적으로 실패
- **증상** — `$LASTEXITCODE` 빈값+terraform 출력 0줄인데 "init failed" throw(직접 실행은 항상 성공), mojibake.
- **원인** — Write 도구가 만든 BOM 없는 UTF-8 `.ps1`을 PS5.1이 cp949로 읽어, 한글 주석의 UTF-8 멀티바이트가 다음 코드 라인(`& terraform init`)을 주석으로 삼킴 → 명령 미실행. 편집마다 바이트패턴이 바뀌어 간헐적으로 보임.
- **조치** — 스크립트 전체를 ASCII 전용으로 재작성(순수 ASCII는 cp949·UTF-8 동일).
- **느낀점** — 한글 주석 한 줄이 그 다음 실행문을 삼킬 수 있다. 이 머신의 `.ps1`은 ASCII 전용.

### 2026-07-03 · [infra] — Karpenter 라이브 브링업 (버전 panic + helm false-green + IAM GC)
- **증상** — 컨트롤러가 시작 즉시 CrashLoopBackOff인데 terraform apply는 green.
- **원인** — ① 차트 1.1.1이 K8s 1.34에서 즉시 panic(존재하지만 미지원 버전) ② `helm wait=true`가 시작-즉시-panic형 CrashLoop을 못 잡고 통과 ③ 모듈 v20 권한셋에 1.13 GC가 쓰는 `iam:ListInstanceProfiles`가 없어 매 리컨실 AccessDenied.
- **조치** — 1.13.0 업그레이드 + apply 후 kubectl로 1/1 확인 필수화 + 스코프 IAM 1문 보충. 이후 스팟 ~30초 프로비저닝·회수까지 실검증.
- **느낀점** — 차트 버전은 '존재'가 아니라 'K8s 호환 매트릭스'로 봐야 하고, terraform green은 런타임 healthy를 보장하지 않는다.

### 2026-07-03 · [infra] — backend destroy에서 Lambda Hyperplane ENI가 SG를 ~25분 붙잡음
- **증상** — SG 삭제가 계속 재시도.
- **원인** — Lambda ENI가 함수 삭제 후에도 `in-use` 유지 — available 전환까지 ~25분(그동안 Lambda 서비스 소유라 강제삭제 불가).
- **조치** — available 되는 즉시 수동 삭제 → SG 통과. 코드 하드닝: SG `timeouts{delete="40m"}`.
- **느낀점** — ENI가 리소스 삭제를 막는 패턴(고아 pod ENI·Hyperplane ENI 동류). in-use 동안은 대기가 유일.

### 2026-07-03 · [infra] — shared destroy 막바지 IGW detach가 DependencyViolation (NAT 레이스)
- **증상** — "has some mapped public addresses"로 IGW 삭제 실패.
- **원인** — IGW 삭제 재시도가 NAT 인스턴스 종료(41초)와 레이스해 public IP 매핑이 남은 시점에 마지막 시도를 침.
- **조치** — `aws_instance.nat`에 `depends_on=[module.vpc]` — destroy 역순에서 NAT가 IGW보다 항상 먼저 삭제.
- **느낀점** — destroy 순서 레이스는 생성 순서 의존성으로 강제해 없앤다.

### 2026-07-03 · [contracts·infra] — Lambda 패키징 데이터파일·psycopg2 함정
- **증상** — 런타임에 contracts 파일을 못 찾거나 psycopg2 import 실패 위험.
- **원인** — 패키지가 contracts를 `__file__` 상대경로로 로드하는데 zip에 패키지만 담으면 못 찾음. psycopg2는 C확장이라 로컬(win/mac) 설치본을 zip하면 Lambda(리눅스) import 실패.
- **조치** — zip 루트에 패키지+contracts 나란히 복사 + `pip --platform manylinux2014_x86_64 --only-binary`로 리눅스 휠 강제.
- **느낀점** — 상대경로 로드·네이티브 확장은 패키징 시 런타임 환경(경로·아키텍처)을 그대로 재현해야 한다.

### 2026-07-03 · [apps-console] — real pg 경로가 배포돼도 런타임 module not found 위험
- **증상** — `use_mock` 기본이 false라 실 pg가 기본 경로인데 배포 zip에 node_modules 없음.
- **원인** — `archive_file`이 dist/만 zip하는데 tsc 산출물은 pg를 런타임 require로 남김.
- **조치** — tsc→esbuild 번들(`--bundle --external:@aws-sdk/*` — pg는 인라인).
- **느낀점** — 번들 없이 tsc만 하면 VPC Lambda에서 의존성이 사라진다. 배포 전 실 런타임 기준으로 확인.

### 2026-07-03 · [rag] — RAG model ID가 bare name이라 실 Bedrock 404 (mock만 돌아 안 드러남)
- **증상** — 실 RAG 호출 시 404 예상(mock 데모만 돌아 안 드러남).
- **원인** — `anthropic.claude-sonnet-4-5`는 별칭이지 Bedrock invoke ID가 아님.
- **조치** — `list-inference-profiles`로 실 Global 프로파일 확정.
- **느낀점** — mock만 돌리면 실 API에서만 터지는 ID 오류가 숨는다.

### 2026-07-02 · [infra] — apply 직전 객관 리뷰로 잡은 apply-blocker 3건
- **증상** — plan은 클린인데 apply-time에 실패하거나 비용이 6배가 될 상태.
- **원인** — ① EKS 1.30이 EXTENDED_SUPPORT라 컨트롤플레인 $0.10→$0.60/h(6배) ② RDS 16.4가 서울에서 제거됨(엔진버전은 apply-time 검증) ③ RDS 마스터 시크릿 `recovery_window` 미지정(기본 30일)→destroy 후 이름 점유→2번째 apply의 CreateSecret 실패.
- **조치** — `describe-*-versions`로 확인해 1.34/16.9로, `recovery_window_in_days=0`.
- **느낀점** — plan이 통과해도 apply-time API 검증(엔진 버전·비용 계층)은 못 잡는다. 돈 쓰기 전에 API로 사전 확인.

### 2026-07-02 · [engine·infra] — 독립 리뷰가 잡은 버그 2건
- **증상** — `finding_explanations.confidence_score`가 항상 NULL·반환 verdict 항상 null / ACM 빈 cert면 apply 하드실패.
- **원인** — ① case 빌더는 verdict·confidence를 `evidence_meta`에 쓰는데 핸들러가 `reasoning`에서 읽음(한쪽만 diverge) ② `acm_certificate_arn` 빈값이면 HTTPS 리스너가 하드실패.
- **조치** — ① 둘 다 evidence_meta에서 읽기 ② HTTPS 리스너 `count` 가드 + HTTP 폴백.
- **느낀점** — 같은 데이터를 두 코드가 서로 다른 dict에서 읽으면 한쪽만 조용히 NULL이 된다.

### 2026-07-02 · [attackpath·infra] — ArgoCD glob이 depth1만 잡아 앱 0개 배포
- **증상** — ArgoCD가 앱 매니페스트를 배포하지 않음.
- **원인** — ① `k8s/*.yaml`만 두면 글롭 `*`가 `/`를 안 넘어 depth1 namespace만 잡고 앱(depth2) 0개 ② 매니페스트 IRSA 역할명이 infra와 불일치(`cnapp-target-*` vs `cnapp-agentic-target-*`).
- **조치** — `{k8s/*.yaml,*/k8s/*.yaml}` + 역할명 정정.
- **느낀점** — ArgoCD 글롭의 `*`는 디렉터리 경계를 안 넘는다. depth를 명시해야 한다.

### 2026-07-02 · [infra] — plan이 SG description ASCII 위반을 apply 전에 차단
- **증상** — plan이 shared rds SG 규칙에서 exit 1.
- **원인** — AWS 보안그룹 description은 charset 제한이라 한글·em대시·가운뎃점 불가 — 4곳에 비ASCII.
- **조치** — 4곳 전부 ASCII로 교정.
- **느낀점** — plan이 돈 쓰기 전에 잡아준 사례. 레이어드 plan의 가치.

### 2026-07-02 · [engine] — cross_cloud 가설이 한 번도 추가되지 않던 조용한 버그
- **증상** — 데모 Hypothesis 출력에 크로스클라우드 체인 가설이 누락(CI는 통과).
- **원인** — `_has_cross_cloud()`가 `edge.get("edge_type")=="cross_cloud"`를 봤는데 계약 엣지는 `type`+`cross_cloud`(불리언) 구조라 그 키·값이 없음 → 항상 False. 골든 검증이 가설 목록을 안 봐 CI 미탐.
- **조치** — `edge.get("cross_cloud")`(불리언)로 수정.
- **느낀점** — 계약 필드명을 틀리면 조용히 항상 False가 되고, 그 출력을 검증에서 안 보면 CI도 못 잡는다.

### 2026-07-01 · [infra] — infra/shared terraform init provider 버전 충돌 (fck-nat)
- **증상** — init이 provider 버전 충돌로 실패.
- **원인** — fck-nat 모듈이 `aws>=6.0`을 요구하는데 vpc/eks 모듈은 5.x(`<6.0`).
- **조치** — fck-nat 모듈을 raw NAT instance(공개 AMI + `source_dest_check=false` + private route)로 교체.
- **느낀점** — 모듈 하나의 provider 제약이 스택 전체 init을 막을 수 있다. 얇은 raw 리소스가 오히려 안전.

### 2026-07-01 · [apps-target] — member 로컬 uvicorn 기동 실패 (Python 3.8 PEP585)
- **증상** — 로컬 uvicorn 기동 시 TypeError(Docker 3.12는 정상).
- **원인** — 로컬 기본 python이 3.8인데 코드가 빌트인 제네릭(`list[Member]`)을 써 FastAPI `response_model` 런타임 평가에서 실패.
- **조치** — `typing.List/Dict`로 교체(3.8+ 호환).
- **느낀점** — 로컬/컨테이너 파이썬 버전 차이가 런타임 타입 평가에서만 드러난다.

### 2026-07-01 · [contracts] — 진우 커밋 pull 후 validate.py 2건 FAIL (main RED)
- **증상** — pull 직후 `validate.py` 2건 FAIL(CI red).
- **원인** — 병합이 f5 `resource_id`를 옛 값으로 리버트해 타입과 불일치, f17이 재매핑됐으나 pillar가 안 맞음.
- **조치** — f5 캐논 값 복원, f17 카탈로그 재추가 후 재매핑 → 통과.
- **느낀점** — 계약 파일은 pull 즉시 검증기를 돌려야 한다. 병합이 이전 수정을 조용히 리버트할 수 있다.
