import { useSystem } from '@/api/queries'
import { StatCard } from '@/components/StatCard'
import { Card, SectionTitle, Badge, Skeleton, ErrorNote } from '@/components/ui'

// AI·시스템 관측 — "AI가 어떻게 돌아가는지"를 콘솔 한 화면에서.
// 모델 구성(챗/임베딩/엔진) · RAG 지식베이스(pgvector) · Bedrock 사용량(CloudWatch 24h) · 데이터 현황.

const PIPELINE = [
  { icon: '📡', label: '스캐너', sub: 'CSPM·CIEM·워크로드' },
  { icon: '📥', label: '수집', sub: 'EventBridge→SQS' },
  { icon: '🧹', label: '정규화', sub: 'OCSF-lite' },
  { icon: '🕸️', label: '상관', sub: 'attack-path R1~R5' },
  { icon: '⚖️', label: '트리아지', sub: '비용 게이트' },
  { icon: '🔎', label: 'Evidence', sub: 'AI tool-use 조사' },
  { icon: '🧠', label: 'Reasoning', sub: '판정·내러티브' },
  { icon: '🖥️', label: '콘솔', sub: '이 화면' },
]

function num(v: number): string {
  if (v < 0) return '—'
  return v.toLocaleString()
}

function ModelCard({ role, model, desc, badge }: { role: string; model: string; desc: string; badge: string }) {
  return (
    <Card hover className="p-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">{role}</p>
        <Badge tone="brand">{badge}</Badge>
      </div>
      <p className="mt-2 break-all rounded-lg bg-slate-50 px-2.5 py-1.5 font-mono text-[11px] text-slate-700">{model}</p>
      <p className="mt-2 text-xs leading-relaxed text-slate-500">{desc}</p>
    </Card>
  )
}

export default function System() {
  const { data, isLoading, isError, error } = useSystem()

  if (isLoading)
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-52" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  if (isError) return <ErrorNote message={(error as Error)?.message} />
  if (!data) return null

  const cwFail = data.bedrock.invocations24h < 0

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">AI·시스템</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            에이전틱 AI 엔진 · RAG 지식베이스 · Bedrock 사용량을 한 화면에서 관측
          </p>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
            data.live ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${data.live ? 'animate-pulse bg-emerald-500' : 'bg-amber-500'}`} />
          {data.live ? 'LIVE — 실 RDS·CloudWatch 집계' : '목업 데이터'}
        </span>
      </div>

      {/* 데이터 파이프라인 스트립 */}
      <Card className="overflow-x-auto p-4">
        <SectionTitle>데이터 파이프라인 (agentless — 타깃과 직접 통신 없음)</SectionTitle>
        <div className="flex min-w-max items-stretch gap-1.5">
          {PIPELINE.map((s, i) => (
            <div key={s.label} className="flex items-center gap-1.5">
              <div
                className={`flex w-[92px] flex-col items-center rounded-xl border px-2 py-2.5 text-center ${
                  s.label === 'Evidence' || s.label === 'Reasoning'
                    ? 'border-brand-200 bg-brand-50/60'
                    : 'border-slate-200 bg-slate-50/60'
                }`}
              >
                <span className="text-base leading-none">{s.icon}</span>
                <span className="mt-1 text-xs font-semibold text-slate-700">{s.label}</span>
                <span className="mt-0.5 text-[10px] leading-tight text-slate-400">{s.sub}</span>
              </div>
              {i < PIPELINE.length - 1 && <span className="text-slate-300">→</span>}
            </div>
          ))}
        </div>
      </Card>

      {/* Bedrock 사용량(24h) */}
      <div>
        <SectionTitle
          action={
            <span className="text-[11px] text-slate-400">
              {cwFail ? 'CloudWatch 집계 불가(권한/전파 확인)' : 'CloudWatch AWS/Bedrock 지표 · 최근 24시간 · 전 모델 합산'}
            </span>
          }
        >
          🧠 Bedrock 사용량 (24h)
        </SectionTitle>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StatCard label="모델 호출" value={num(data.bedrock.invocations24h)} accent="brand" icon="⚡" hint="Converse·InvokeModel 합산" />
          <StatCard label="입력 토큰" value={num(data.bedrock.inputTokens24h)} accent="blue" icon="📥" hint="프롬프트+컨텍스트" />
          <StatCard label="출력 토큰" value={num(data.bedrock.outputTokens24h)} accent="amber" icon="📤" hint="모델 생성분" />
        </div>
      </div>

      {/* 모델 구성 */}
      <div>
        <SectionTitle>🤖 AI 모델 구성 (Amazon Bedrock · 서울/글로벌 프로파일)</SectionTitle>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <ModelCard
            role="능동조사 엔진 (Evidence)"
            model={data.models.engine}
            badge="tool-use"
            desc="LLM이 read-only AWS API(계약④ allowlist 9종)를 스스로 골라 호출해 증거를 수집 — '챗봇 탈출'의 심장. 트리아지 게이트 통과 케이스만 조사(비용 통제)."
          />
          <ModelCard
            role="AI 어시스턴트 (RAG 답변)"
            model={data.models.chat}
            badge="RAG"
            desc="질문을 Titan으로 임베딩 → pgvector 코사인 유사도 검색(top-4) → 검색된 지식베이스 청크를 근거로 답변 생성. CHAT_MODEL_ID env로 무코드 스왑 가능."
          />
          <ModelCard
            role="임베딩 (지식베이스·질의)"
            model={data.models.embed}
            badge={`${data.rag.dim}-dim`}
            desc="지식베이스 적재와 질의 임베딩에 동일 모델 사용(벡터 정합). 정규화된 벡터로 pgvector 코사인 거리 검색."
          />
        </div>
      </div>

      {/* RAG 지식베이스 + 데이터 현황 */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card className="p-5">
          <SectionTitle>📚 RAG 지식베이스 (RDS PostgreSQL + pgvector)</SectionTitle>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-3xl font-bold tabular-nums text-brand-600">{num(data.rag.chunks)}</p>
              <p className="text-xs text-slate-400">지식 청크 (rag_chunks)</p>
            </div>
            <div>
              <p className="text-3xl font-bold tabular-nums text-slate-900">{num(data.rag.controls)}</p>
              <p className="text-xs text-slate-400">커버 control 종수</p>
            </div>
          </div>
          <div className="mt-4 space-y-1.5 text-xs text-slate-500">
            <p className="flex items-center gap-1.5">
              <Badge tone="brand">벡터</Badge> {data.rag.dim}차원 · {data.rag.index} 인덱스 · 코사인 유사도(<code className="font-mono">embedding &lt;=&gt; query</code>)
            </p>
            <p className="flex items-center gap-1.5">
              <Badge tone="slate">경로</Badge> Titan Embed v2 → pgvector top-4 → Bedrock 답변(근거 control 표시)
            </p>
          </div>
        </Card>

        <Card className="p-5">
          <SectionTitle>🗄️ 데이터 현황 (findings 저장소)</SectionTitle>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-3xl font-bold tabular-nums text-rose-600">{num(data.data.findingsOpen)}</p>
              <p className="text-xs text-slate-400">open findings</p>
            </div>
            <div>
              <p className="text-3xl font-bold tabular-nums text-slate-900">{num(data.data.findingsTotal)}</p>
              <p className="text-xs text-slate-400">전체 findings</p>
            </div>
            <div>
              <p className="text-3xl font-bold tabular-nums text-red-600">{num(data.data.attackPaths)}</p>
              <p className="text-xs text-slate-400">attack-path (크로스클라우드 상관)</p>
            </div>
            <div>
              <p className="text-3xl font-bold tabular-nums text-brand-600">{num(data.data.cases)}</p>
              <p className="text-xs text-slate-400">AI 조사 케이스 (cases)</p>
            </div>
          </div>
          <p className="mt-4 text-xs text-slate-400">
            스캐너 → 정규화(OCSF-lite) → RDS 적재 → 상관·조사 후 이 콘솔이 read-only로 표시.
          </p>
        </Card>
      </div>

      {/* 더 깊은 관측 */}
      <Card className="p-5">
        <SectionTitle>🔭 더 깊은 관측 (플랫폼 운영 관제)</SectionTitle>
        <ul className="space-y-1.5 text-sm text-slate-600">
          <li className="flex items-start gap-2">
            <Badge tone="aws" className="mt-0.5 shrink-0">CloudWatch</Badge>
            <span>
              대시보드 <code className="rounded bg-slate-100 px-1 font-mono text-xs">cnapp-agentic-platform</code> — Lambda 6종·SQS·RDS·Step Functions·Bedrock 토큰/비용·엔진 EMF 24위젯
            </span>
          </li>
          <li className="flex items-start gap-2">
            <Badge tone="brand" className="mt-0.5 shrink-0">Grafana</Badge>
            <span>EKS 내 kube-prometheus-stack — EKS/애플리케이션/인프라/AI 분야별 대시보드 4종(31패널)</span>
          </li>
          <li className="flex items-start gap-2">
            <Badge tone="slate" className="mt-0.5 shrink-0">감사</Badge>
            <span>모든 조치 실행은 S3 Object Lock 불변 기록 — 감사로그 탭에서 조회</span>
          </li>
        </ul>
      </Card>
    </div>
  )
}
