import { useSearchParams } from 'react-router-dom'
import { useFindings, type FindingsFilter } from '@/api/queries'
import { PillarFilter } from '@/components/PillarFilter'
import { FindingCard } from '@/components/FindingCard'
import { EmptyState } from '@/components/EmptyState'
import { Card, SkeletonRows, ErrorNote } from '@/components/ui'
import { SEVERITY_LABEL, SEVERITY_DOT } from '@/lib/severity'
import type { SeverityId } from '@/api/types'

// 필터를 URL 쿼리 파라미터에 실어서, finding 상세로 들어갔다 뒤로가기해도
// 브라우저 history가 그대로 필터 상태를 복원하게 한다(로컬 useState는 라우트
// 이동 시 컴포넌트가 언마운트되며 초기화돼 이 문제가 있었음).
export default function Findings() {
  const [searchParams, setSearchParams] = useSearchParams()
  const filter: FindingsFilter = {
    cloud: searchParams.get('cloud') ?? undefined,
    pillar: searchParams.get('pillar') ?? undefined,
    status: searchParams.get('status') ?? undefined,
    sort: searchParams.get('sort') ?? 'priority',
  }
  const setFilter = (f: FindingsFilter) => {
    const next = new URLSearchParams()
    if (f.cloud) next.set('cloud', f.cloud)
    if (f.pillar) next.set('pillar', f.pillar)
    if (f.status) next.set('status', f.status)
    if (f.sort) next.set('sort', f.sort)
    setSearchParams(next)
  }
  const { data, isLoading, isError, error, refetch, isFetching } = useFindings(filter)

  const rows = data ?? []
  const sevCounts = ([1, 2, 3, 4, 5] as SeverityId[]).map((s) => ({
    s,
    n: rows.filter((f) => f.severity_id === s).length,
  }))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Findings</h1>
          <p className="mt-0.5 text-sm text-slate-500">정규화된 보안 발견사항 — 우선순위 순</p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 shadow-sm transition hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50"
        >
          <span className={isFetching ? 'inline-block animate-spin' : 'inline-block'}>↻</span>
          {isFetching ? '새로고침 중…' : '새로고침'}
        </button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <PillarFilter filter={filter} onChange={setFilter} />
        {/* 심각도 집계 */}
        {!isLoading && rows.length > 0 && (
          <div className="flex items-center gap-1.5 text-xs">
            {sevCounts
              .filter((c) => c.n > 0)
              .map(({ s, n }) => (
                <span key={s} className="flex items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">
                  <span className={`inline-block h-2 w-2 rounded-full ${SEVERITY_DOT[s]}`} />
                  {SEVERITY_LABEL[s]} {n}
                </span>
              ))}
          </div>
        )}
      </div>

      <Card className="overflow-hidden">
        {isLoading ? (
          <SkeletonRows rows={8} />
        ) : isError ? (
          <div className="p-4">
            <ErrorNote message={(error as Error)?.message} />
          </div>
        ) : rows.length > 0 ? (
          <>
            <div className="border-b border-slate-100 bg-slate-50/70 px-4 py-2 text-xs font-medium text-slate-500">총 {rows.length}건</div>
            {rows.map((f) => (
              <FindingCard key={f.finding_id} f={f} />
            ))}
          </>
        ) : (
          <EmptyState title="조건에 맞는 finding 없음" hint="필터를 바꿔보세요" />
        )}
      </Card>
    </div>
  )
}
