// 빈 상태 처리(§2.1) — 빈 캔버스 대신 안내 placeholder.
export function EmptyState({ title, hint, icon = '📭' }: { title: string; hint?: string; icon?: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white/50 py-16 text-center">
      <span className="text-3xl opacity-60">{icon}</span>
      <p className="mt-3 text-sm font-medium text-slate-600">{title}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  )
}
