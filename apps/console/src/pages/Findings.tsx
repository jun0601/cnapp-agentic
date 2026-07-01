import { useState } from 'react'
import { useFindings, type FindingsFilter } from '@/api/queries'
import { PillarFilter } from '@/components/PillarFilter'
import { FindingCard } from '@/components/FindingCard'
import { EmptyState } from '@/components/EmptyState'

export default function Findings() {
  const [filter, setFilter] = useState<FindingsFilter>({ sort: 'priority' })
  const { data, isLoading, refetch } = useFindings(filter)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Findings</h1>
        <button
          onClick={() => refetch()}
          className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
        >
          새로고침
        </button>
      </div>

      <PillarFilter filter={filter} onChange={setFilter} />

      <div className="overflow-hidden rounded-lg border">
        {isLoading ? (
          <EmptyState title="불러오는 중…" />
        ) : data && data.length > 0 ? (
          <>
            <div className="border-b bg-slate-50 px-4 py-2 text-xs text-slate-500">{data.length}건</div>
            {data.map((f) => (
              <FindingCard key={f.finding_id} f={f} />
            ))}
          </>
        ) : (
          <EmptyState title="조건에 맞는 finding 없음" hint="필터를 바꿔보세요" />
        )}
      </div>
    </div>
  )
}
