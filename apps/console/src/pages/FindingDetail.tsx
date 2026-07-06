import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useFinding } from '@/api/queries'
import { SeverityBadge } from '@/components/SeverityBadge'
import { EvidenceTab } from '@/components/EvidenceTab'
import { Card, Badge, Skeleton, ErrorNote } from '@/components/ui'
import { PILLAR_LABEL } from '@/lib/severity'
import type { FindingExplanation } from '@/api/types'

type Tab = 'explanation' | 'evidence'

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
          <div>sources: {f.sources.join(', ')}</div>
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
