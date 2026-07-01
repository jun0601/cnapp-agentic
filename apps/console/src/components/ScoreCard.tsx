// secure score 요약 카드(§2.0 — AWS 크게 / Azure 보조).
export function ScoreCard({
  cloud,
  score,
  label,
  emphasis,
}: {
  cloud: 'aws' | 'azure'
  score: number
  label: string
  emphasis?: boolean
}) {
  const color = cloud === 'aws' ? 'text-aws' : 'text-azure'
  return (
    <div className={`rounded-lg border bg-white p-5 ${emphasis ? 'ring-2 ring-slate-900/5' : ''}`}>
      <div className="flex items-center justify-between">
        <span className={`text-sm font-semibold uppercase ${color}`}>{cloud}</span>
        <span className="text-xs text-slate-400">{label}</span>
      </div>
      <div className={`mt-2 font-bold ${emphasis ? 'text-5xl' : 'text-3xl'}`}>
        {score}
        <span className="ml-1 text-base font-normal text-slate-400">/100</span>
      </div>
    </div>
  )
}
