import { Link } from 'react-router-dom'
import type { Finding } from '@/api/types'
import { SeverityBadge } from './SeverityBadge'
import { PILLAR_LABEL } from '@/lib/severity'

const AI_BADGE: Record<Finding['ai_status'], string> = {
  done: 'bg-emerald-100 text-emerald-700',
  pending: 'bg-amber-100 text-amber-700',
  failed: 'bg-rose-100 text-rose-700',
}
const AI_LABEL: Record<Finding['ai_status'], string> = {
  done: 'AI 분석완료',
  pending: 'AI 대기',
  failed: 'AI 실패',
}

export function FindingCard({ f }: { f: Finding }) {
  return (
    <Link
      to={`/findings/${f.finding_id}`}
      className="flex items-center gap-3 border-b bg-white px-4 py-3 text-sm hover:bg-slate-50"
    >
      <SeverityBadge id={f.severity_id} />
      <span className={`rounded px-1.5 py-0.5 text-xs font-semibold uppercase ${f.cloud === 'aws' ? 'text-aws' : 'text-azure'}`}>
        {f.cloud}
      </span>
      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">{PILLAR_LABEL[f.pillar]}</span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-slate-800">{f.title}</p>
        <p className="truncate font-mono text-xs text-slate-400">{f.resource_id}</p>
      </div>
      {f.attack_path_id && (
        <span className="rounded bg-red-50 px-1.5 py-0.5 text-xs font-semibold text-red-600">경로</span>
      )}
      <span className={`rounded px-1.5 py-0.5 text-xs ${AI_BADGE[f.ai_status]}`}>{AI_LABEL[f.ai_status]}</span>
      <span
        className={`rounded px-1.5 py-0.5 text-xs ${
          f.status === 'open' ? 'bg-slate-100 text-slate-600' : f.status === 'remediated' ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-400'
        }`}
      >
        {f.status}
      </span>
    </Link>
  )
}
