import { Link } from 'react-router-dom'
import type { Finding } from '@/api/types'
import { SeverityBadge } from './SeverityBadge'
import { PILLAR_LABEL } from '@/lib/severity'
import { Badge } from './ui'

const AI: Record<Finding['ai_status'], { tone: 'emerald' | 'amber' | 'red'; label: string }> = {
  done: { tone: 'emerald', label: 'AI 완료' },
  pending: { tone: 'amber', label: 'AI 대기' },
  failed: { tone: 'red', label: 'AI 실패' },
}
const SEV_BAR: Record<number, string> = { 1: 'bg-sev-1', 2: 'bg-sev-2', 3: 'bg-sev-3', 4: 'bg-sev-4', 5: 'bg-sev-5' }

export function FindingCard({ f }: { f: Finding }) {
  return (
    <Link
      to={`/findings/${f.finding_id}`}
      className="group flex items-stretch border-b border-slate-100 bg-white text-sm transition last:border-0 hover:bg-slate-50/70"
    >
      {/* 좌측 심각도 컬러바 — 빠른 스캔 */}
      <span className={`w-1 shrink-0 ${SEV_BAR[f.severity_id]}`} aria-hidden />
      <div className="flex flex-1 items-center gap-3 px-4 py-3.5">
        <SeverityBadge id={f.severity_id} />
        <span className={`text-xs font-bold uppercase ${f.cloud === 'aws' ? 'text-aws' : 'text-azure'}`}>{f.cloud}</span>
        <Badge tone="slate">{PILLAR_LABEL[f.pillar]}</Badge>
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium text-slate-800">{f.title}</p>
          <p className="truncate font-mono text-xs text-slate-400">{f.resource_id}</p>
        </div>
        {f.attack_path_id && <Badge tone="red">🛑 경로</Badge>}
        <Badge tone={AI[f.ai_status].tone}>{AI[f.ai_status].label}</Badge>
        <span
          className={`w-20 shrink-0 rounded-full px-2 py-0.5 text-center text-xs font-medium ${
            f.status === 'open'
              ? 'bg-slate-100 text-slate-600'
              : f.status === 'remediated'
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-slate-100 text-slate-400'
          }`}
        >
          {f.status}
        </span>
        <span className="shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-400">→</span>
      </div>
    </Link>
  )
}
