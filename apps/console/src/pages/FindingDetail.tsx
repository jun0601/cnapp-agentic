import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useFinding } from '@/api/queries'
import { SeverityBadge } from '@/components/SeverityBadge'
import { EvidenceTab } from '@/components/EvidenceTab'
import { Card, Skeleton, ErrorNote } from '@/components/ui'
import { PILLAR_LABEL } from '@/lib/severity'
import type { FindingExplanation } from '@/api/types'

type Tab = 'explanation' | 'evidence'

// AI 설명 카드(UC1) — ai_status≠done이면 placeholder(§15.4). finding 본문은 항상 표시.
function ExplanationCard({ ex }: { ex: FindingExplanation | null }) {
  if (!ex || ex.ai_status !== 'done') {
    const msg =
      ex?.ai_status === 'failed'
        ? 'AI 분석 실패 — 스캐너 데이터는 정상입니다.'
        : 'AI 분석 대기/진행 중입니다.'
    return (
      <div className="rounded-lg border border-dashed bg-white p-6 text-sm text-slate-500">{msg}</div>
    )
  }
  return (
    <div className="space-y-3 rounded-lg border bg-white p-5 text-sm">
      <div>
        <h4 className="text-xs font-semibold uppercase text-slate-400">요약</h4>
        <p className="mt-1 text-slate-700">{ex.summary}</p>
      </div>
      <div>
        <h4 className="text-xs font-semibold uppercase text-slate-400">왜 위험한가</h4>
        <p className="mt-1 text-slate-700">{ex.why}</p>
      </div>
      <div>
        <h4 className="text-xs font-semibold uppercase text-slate-400">조치 방법</h4>
        <p className="mt-1 text-slate-700">{ex.how}</p>
      </div>
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

  return (
    <div className="space-y-5">
      <Link to="/findings" className="text-sm text-slate-500 hover:underline">
        ← Findings
      </Link>

      {/* finding 본문 — 항상 표시(AI 죽어도 산다) */}
      <div className="rounded-lg border bg-white p-5">
        <div className="flex items-center gap-2">
          <SeverityBadge id={f.severity_id} />
          <span className={`text-xs font-semibold uppercase ${f.cloud === 'aws' ? 'text-aws' : 'text-azure'}`}>
            {f.cloud}
          </span>
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">{PILLAR_LABEL[f.pillar]}</span>
          <span className="ml-auto text-xs text-slate-400">{f.status}</span>
        </div>
        <h1 className="mt-2 text-lg font-bold">{f.title}</h1>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-slate-500">
          <div className="col-span-2 font-mono text-slate-600">{f.resource_id}</div>
          <div>control: {f.control_id}</div>
          <div>sources: {f.sources.join(', ')}</div>
          {f.attack_path_id && (
            <div className="col-span-2">
              attack-path:{' '}
              <Link to={`/attack-paths/${f.attack_path_id}`} className="text-red-600 hover:underline">
                {f.attack_path_id}
              </Link>
            </div>
          )}
        </dl>
      </div>

      {/* 탭 */}
      <div className="flex gap-1 border-b text-sm">
        {(['explanation', 'evidence'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 ${tab === t ? 'border-b-2 border-slate-900 font-semibold' : 'text-slate-500'}`}
          >
            {t === 'explanation' ? 'AI 설명' : '능동조사 (Evidence)'}
          </button>
        ))}
      </div>

      {tab === 'explanation' ? <ExplanationCard ex={explanation} /> : <EvidenceTab evidenceCase={evidenceCase} />}
    </div>
  )
}
