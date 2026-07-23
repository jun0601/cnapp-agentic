import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useFinding, useReanalyze } from '@/api/queries'
import { SeverityBadge } from '@/components/SeverityBadge'
import { EvidenceTab } from '@/components/EvidenceTab'
import { Card, Badge, Skeleton, ErrorNote } from '@/components/ui'
import { PILLAR_LABEL } from '@/lib/severity'
import { useRole } from '@/lib/auth'
import type { FindingExplanation } from '@/api/types'

type Tab = 'explanation' | 'evidence'

// sources는 실 스캔(예: Trivy CVE 나열)에서 수십~수백 개까지 늘어날 수 있어 grid 셀이 그대로
// 깨짐 — 앞 5개만 보이고 나머지는 토글로 펼침/접음(2026-07-22).
function SourcesList({ sources }: { sources?: string[] }) {
  const [expanded, setExpanded] = useState(false)
  if (!sources || sources.length === 0) return <>—</>
  const LIMIT = 5
  const remaining = sources.length - LIMIT
  const shown = expanded ? sources : sources.slice(0, LIMIT)
  return (
    <span>
      {shown.join(', ')}
      {remaining > 0 && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="ml-1.5 font-semibold text-brand-600 hover:underline"
        >
          {expanded ? '접기' : `+${remaining}개 더보기`}
        </button>
      )}
    </span>
  )
}

// AI 설명 카드(UC1) — ai_status≠done이면 placeholder(§15.4). finding 본문은 항상 표시.
function ExplanationCard({ ex }: { ex: FindingExplanation | null }) {
  if (!ex || ex.ai_status !== 'done') {
    const msg = ex?.ai_status === 'failed' ? 'AI 분석 실패 — 스캐너 데이터는 정상입니다.' : 'AI 분석 대기/진행 중입니다.'
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-dashed border-slate-300 bg-white/60 p-6 text-sm text-slate-500">
        <span>🤖</span> {msg}
      </div>
    )
  }
  const items = [
    { icon: '📌', label: '요약', text: ex.summary },
    { icon: '⚠️', label: '왜 위험한가', text: ex.why },
    { icon: '🛠️', label: '조치 방법', text: ex.how },
  ]
  return (
    <div className="space-y-3">
      {items.map((it) => (
        <Card key={it.label} className="p-4">
          <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
            <span>{it.icon}</span> {it.label}
          </h4>
          <p className="mt-1.5 text-sm leading-relaxed text-slate-700">{it.text}</p>
        </Card>
      ))}
    </div>
  )
}

// 🤖 AI 재조사(라이브 트리거) — approver만. 백엔드가 orchestrator Lambda를 비동기 invoke →
// 실 Bedrock이 read-only API tool-use로 재조사 → cases·설명 갱신(1~2분, 지연 invalidate로 반영).
function ReanalyzeButton({ findingId }: { findingId: string }) {
  const role = useRole()
  const m = useReanalyze(findingId)
  if (role !== 'approver') return null
  return (
    <div className="flex items-center justify-end gap-2.5">
      {m.isSuccess && (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
          조사 시작됨 — AI가 read-only API로 증거 수집 중 (1~2분 후 자동 갱신)
        </span>
      )}
      {m.isError && <span className="text-xs text-rose-600">트리거 실패: {(m.error as Error)?.message}</span>}
      <button
        onClick={() => m.mutate()}
        disabled={m.isPending || m.isSuccess}
        className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold shadow-sm transition ${
          m.isSuccess
            ? 'cursor-default bg-emerald-100 text-emerald-700'
            : 'bg-gradient-to-r from-brand-600 to-violet-600 text-white hover:opacity-90 disabled:opacity-60'
        }`}
      >
        {m.isPending ? '트리거 중…' : m.isSuccess ? '🔬 조사 진행 중' : '🤖 AI 재조사 실행'}
      </button>
    </div>
  )
}

export default function FindingDetail() {
  const { id } = useParams()
  const { data, isLoading, isError, error } = useFinding(id)
  const [tab, setTab] = useState<Tab>('explanation')

  if (isLoading)
    return (
      <div className="space-y-4">
        <Skeleton className="h-4 w-20" />
        <Card className="p-5">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="mt-3 h-6 w-3/4" />
          <Skeleton className="mt-3 h-4 w-1/2" />
        </Card>
      </div>
    )
  if (isError) return <ErrorNote message={(error as Error)?.message} />
  if (!data) return <p className="text-sm text-slate-500">finding을 찾을 수 없습니다.</p>

  const { finding: f, explanation, case: evidenceCase } = data
  const tabs: { id: Tab; label: string }[] = [
    { id: 'explanation', label: '💬 AI 설명' },
    { id: 'evidence', label: '🔎 능동조사 (Evidence)' },
  ]

  return (
    <div className="space-y-5">
      <Link
        to="/findings"
        className="inline-flex items-center gap-1 text-sm font-medium text-slate-500 transition hover:text-slate-700"
      >
        ← Findings
      </Link>

      {/* finding 본문 — 항상 표시(AI 죽어도 산다) */}
      <Card className="p-5">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge id={f.severity_id} />
          <span className={`text-xs font-bold uppercase ${f.cloud === 'aws' ? 'text-aws' : 'text-azure'}`}>{f.cloud}</span>
          <Badge tone="slate">{PILLAR_LABEL[f.pillar]}</Badge>
          <Badge tone={f.status === 'remediated' ? 'emerald' : 'slate'} className="ml-auto">
            {f.status}
          </Badge>
        </div>
        <h1 className="mt-3 text-xl font-bold tracking-tight text-slate-900">{f.title}</h1>
        <div className="mt-3 rounded-xl bg-slate-50 px-3 py-2 font-mono text-xs text-slate-600">{f.resource_id}</div>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs text-slate-500">
          <div>
            control: <span className="font-mono text-slate-700">{f.control_id}</span>
          </div>
          <div>sources: <SourcesList sources={f.sources} /></div>
          {f.attack_path_id && (
            <div className="col-span-2">
              attack-path:{' '}
              <Link to={`/attack-paths/${f.attack_path_id}`} className="font-semibold text-red-600 hover:underline">
                🛑 {f.attack_path_id}
              </Link>
            </div>
          )}
        </dl>
      </Card>

      {/* AI 재조사 트리거(approver) — 능동조사를 라이브로 재실행 */}
      {id && <ReanalyzeButton findingId={id} />}

      {/* 탭 — 세그먼트 컨트롤 */}
      <div className="flex gap-1 rounded-xl border border-slate-200/70 bg-white p-1 shadow-card">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium transition ${
              tab === t.id ? 'bg-brand-600 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-50'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'explanation' ? <ExplanationCard ex={explanation} /> : <EvidenceTab evidenceCase={evidenceCase} />}
    </div>
  )
}
