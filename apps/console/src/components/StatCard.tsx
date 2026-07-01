import { Card } from './ui'

// KPI 통계 카드 — 보안 대시보드는 숫자로 리드(전체/open/Critical/경로 수).
export function StatCard({
  label,
  value,
  accent = 'slate',
  hint,
}: {
  label: string
  value: number | string
  accent?: 'slate' | 'red' | 'amber' | 'blue'
  hint?: string
}) {
  const accentClass = {
    slate: 'text-slate-900',
    red: 'text-red-600',
    amber: 'text-amber-600',
    blue: 'text-azure',
  }[accent]
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1 text-3xl font-bold tabular-nums ${accentClass}`}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-400">{hint}</p>}
    </Card>
  )
}
