import type { ReactNode } from 'react'
import { Card } from './ui'

// KPI 통계 카드 — 보안 대시보드는 숫자로 리드(전체/open/Critical/경로 수).
type Accent = 'slate' | 'red' | 'amber' | 'blue' | 'brand'
const ACCENT: Record<Accent, { text: string; bar: string }> = {
  slate: { text: 'text-slate-900', bar: 'from-slate-400 to-slate-500' },
  red: { text: 'text-red-600', bar: 'from-red-500 to-rose-600' },
  amber: { text: 'text-amber-600', bar: 'from-amber-400 to-orange-500' },
  blue: { text: 'text-azure', bar: 'from-sky-400 to-blue-600' },
  brand: { text: 'text-brand-600', bar: 'from-brand-500 to-violet-600' },
}

export function StatCard({
  label,
  value,
  accent = 'slate',
  hint,
  icon,
}: {
  label: string
  value: number | string
  accent?: Accent
  hint?: string
  icon?: ReactNode
}) {
  const a = ACCENT[accent]
  return (
    <Card hover className="relative overflow-hidden p-4">
      <div className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${a.bar}`} />
      <div className="flex items-start justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
        {icon && <span className="text-lg leading-none opacity-70">{icon}</span>}
      </div>
      <p className={`mt-2 text-3xl font-bold tabular-nums ${a.text}`}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-400">{hint}</p>}
    </Card>
  )
}
