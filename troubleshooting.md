# 작업 로그 (트러블슈팅 + 진행)

> **이 파일의 역할:** 구현하면서 겪은 **문제·해결(트러블슈팅)**과 **추가·작업한 것(진행)**을 한 줄씩 누적하는 *중앙 운영 로그*. 설계 문서(`docs/`)가 "무엇을 만들지", 이 파일은 "만들면서 실제로 무슨 일이 있었는지".
>
> **왜 영역별 파일이 아니라 중앙 1개인가:** 둘 다 전 영역을 만지므로 중앙집중이 전체 그림을 주고, `[영역]` 태그로 영역별 필터(Ctrl+F `[engine]`)가 가능해 per-area 파일 없이도 분리된다. 흩어놓으면 *영역을 가로지르는 패턴*(예: 권한 문제가 여러 영역에서 반복)을 못 본다.
>
> **기입 형식 (한 줄):** `YYYY-MM-DD / 작성자(준형·진우) / [영역] / 내용`
> **영역 태그:** `[infra]` `[scanners]` `[pipeline]` `[engine]` `[rag]` `[attackpath]` `[apps-target]` `[apps-console]` `[contracts]` `[docs]` `[ci]`
>
> **규칙:** 최신이 위로. 트러블슈팅은 *문제 → 해결*을 한 줄에. 진행 로그는 *무엇을 추가/완료했는지*. 굵직한 설계 변경은 여기 말고 `CLAUDE.md` 변경 로그에(둘은 목적이 다름 — 여기는 작업 디테일, 거기는 pull 알림).

---

## 1. 트러블슈팅 로그 (문제 → 해결)

> 예시(실제 발생 시 이 형식으로 교체·추가):

- `2026-07-01 / 준형 / [apps-console] 외부 리뷰: Evidence 탭 데이터 소스 이중(§5 finding_explanations.evidence_json ↔ §15.4 mock-cases) 발견 → UC0=case단위/UC1=finding단위로 확정, finding_explanations에 case_id FK + cases 테이블 신설, 상세는 finding_id∈case.finding_ids 조인. ai_status placeholder·정합 3건·스택 확정(RF/MSW/TS)+폴리글랏 반영`
- `2026-07-01 / 준형 / [contracts] §2.1 계약 정합 4건 수정 중 attack-path 노드 n4(azure SP)에 대응 finding 부재 발견(assert c 위반) → f16을 골든 경로 편입(control도 ENTRA-SP-CRED-001 신규). validate.py로 4-assert 자동화, CI 게이트(.github/workflows) 추가. validate 통과`
- `2026-07-01 / 준형 / [infra] infra/shared terraform init provider 버전 충돌(fck-nat 모듈 aws>=6.0 vs vpc/eks 5.x <6.0) → fck-nat 모듈을 raw NAT instance(fck-nat 공개 AMI + source_dest_check=false + private route)로 교체해 충돌·모듈 변수 불확실성 동시 제거. fmt·validate 통과`
- `2026-06-30 / 준형 / [contracts] contracts/ 졸업 — 계약 7종 JSON Schema + control-catalog + mock 3종 생성. python json.load 10/10 통과, 교차참조(control_id 카탈로그·dedup_key·골든 경로 id·case finding_ids·evidence allowlist) 정합 검증 통과. 콘솔 출력 cp949 em대시 깨짐은 PYTHONIOENCODING=utf-8로 우회`
- `2026-06-30 / 준형 / [contracts] 검증 후속 확정 — 4.4.1 정규화 규칙 3종(resource_id 캐논·INTERNAL control_id 카탈로그·remediated source별 스코프) 신설, §24 3건 닫음, 2-pass·핵심영역 분담 확정 전환. README 폴더구조 실제 구조로 갱신`
- `2026-06-30 / 준형 / [docs] CLAUDE.md §6·§7이 HEAD~4 머지에서 유실 + §5 "시간 컷" 불릿이 깨진 바이트(ef bf bd)로 잘린 것 발견 → head -126으로 온전부 보존 + HEAD~5에서 §6/§7 추출 복원, §7.1 Next Up 추가`
- `2026-06-30 / 준형 / [contracts] 진우 9개 확정 검증 — attack-path 상관과 Evidence 실행순서 상충 발견(UC0 vs 트리거/게이트) → 2-pass(1차 규칙상관→트리아지 게이트→Evidence→2차 확정)로 docs 통일. dedup용 resource_id 캐논·INTERNAL control_id 카탈로그·remediated 스캐너별 스코프 3건은 §24 미확정 등록`
- `2026-06-30 / 준형 / [docs] project-draft 17~24번이 커밋 cb2c55a에서 파일 꼬리째 유실된 것 발견 → git show 53f8bd6(v5.4)에서 ## 17~끝 구간 추출해 복원, 이음매 빈 줄 정리`
- `2026-06-30 / 준형 / [docs] git pull이 .git/index.lock·ORIG_HEAD.lock stale로 막힘 → del /S /Q .git\*.lock 후 재pull로 해결`
- `2026-07-01 / 준형 / [docs] 진우 문서 검증 6건 총괄 반영 — ①CLAUDE §5 앱분담 stale행(0b1d493 병합 때 되돌아감) → 준형 2개 전담으로 정정 ②project-draft §4.4.1(b) 카탈로그표 누락 control 4행 추가(13→14) ③console §3·§5.1 "D3/Recharts"→React Flow(§15.1 확정) ④f15 title↔control 모순(NOENCRYPT인데 source는 버저닝) → 신규 INTERNAL-S3-LOGGING-DISABLED-001(cspm) 추가 후 재매핑 ⑤§15 모델ID: bare name은 Bedrock invoke ID 아님(404) → Bedrock 형식/inference profile 구현시 확정 주석 ⑥R1 "同 resource" 모호 → "워크로드↔부착 SG 토폴로지" 완화 + 파드→ENI→SG 매핑 주석. 전 md stale 스윕(13종→14종 일괄) + README 역할분담 섹션 추가. validate 통과(14종)`
- `2026-07-01 / 준형 / [contracts] 진우 합의 반영 — f16·f12 객관 기준으로 c463054 값 최종 복원. f16: OVERPRIV-APP-001(의미 느슨)→SP-CRED-001(ciem, title 정확 일치)로 재매핑 + 카탈로그에 INTERNAL-ENTRA-SP-CRED-001 재추가(13종). f12/ECR: pillar vuln→cspm(control도) — "스캔 비활성"은 CVE가 아니라 미스컨피그, 소스가 전부 posture(securityhub ECR.1·config·prowler ecr_scan)라 cspm이 객관. validate OK. 교훈: 기둥=소스 성격 기준을 처음부터 일관 적용할 것`
- `2026-07-01 / 준형 / [contracts] 진우 커밋 0b1d493 pull 후 validate.py 2건 FAIL(main RED) 발견 → f5 resource_id가 aws:eks_pod:shop/order로 리버트돼 type(secret_plaintext)와 assert(b) 불일치 → aws:secret_plaintext:shop/order/AZURE_SP_CRED로 재복원. f17이 ENTRA-RISKY-CONSENT-001(ciem)로 재매핑됐으나 pillar cspm 유지해 assert(a) 위반 → 설계 충실(Azure Defender secure-score=cspm)로 INTERNAL-ENTRA-INSECURE-CFG-001(cspm) 카탈로그 재추가 후 f17 재매핑. validate 통과. ※f16→OVERPRIV-APP-001 재매핑은 CI-green이나 의미 느슨 — 진우 검토 요청`
- `2026-07-01 / 준형 / [apps-console] apps/console 스캐폴드(§15) — Vite+React+TS+Tailwind+TanStack+React Flow+Recharts+MSW. contracts/*.schema.json→타입(손번역 types.ts + gen-types.mjs), MSW handlers가 @contracts alias로 mock-*.json 직접 서빙(vite fs.allow=repoRoot). 화면 8종(핵심 4: Dashboard·Findings·FindingDetail[Evidence탭]·AttackPath + 스텁 4). 트러블: ①tsconfig -b project-ref 제거→tsc --noEmit ②FindingsFilter가 Record 인덱스시그니처 없어 apiGet 타입에러→[key:string] 추가 ③Findings.tsx 손오타(깨진 유니코드) 제거. npm i(252pkg)·msw init·tsc·vite build(499 모듈) 전부 통과`
<!-- 여기부터 실제 항목을 위에 추가 -->

---

## 2. 진행 로그 (추가·작업한 것)

> 무엇을 만들었/추가했는지 한 줄씩. (git 커밋이 1차 기록이지만, 사람이 빠르게 훑는 용도)

- `2026-07-01 / 진우 / [apps-console] Cognito SSO 설계 검증 3건 반영 — authenticate-oidc→authenticate-cognito 전면 교체(project-draft·console-app-design 전 위치), Identity Pool 제거(프론트가 AWS 직접 호출 없음), §7 그룹 클레임 매핑 경로(Entra SAML attr→custom:groups→x-amzn-oidc-data→Lambda 분기) 추가`
- `2026-07-01 / 진우 / [infra] S3 Terraform state 버킷(cnapp-agentic-tfstate, ap-northeast-2) 생성 완료 — 버저닝·SSE-S3·퍼블릭차단 설정. infra/shared main.tf backend bucket 교체, manual-infra.md §2 ✅ 갱신`
- `2026-06-30 / 준형 / [docs] 공통 계약 7종(4.4) + terraform 레이어링·폴더소유(4.6) 확정`
<!-- 여기부터 실제 항목을 위에 추가 -->
