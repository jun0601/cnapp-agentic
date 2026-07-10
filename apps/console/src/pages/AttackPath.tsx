import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAttackPaths } from '@/api/queries'
import { AttackPathGraph } from '@/components/AttackPathGraph'
import { EmptyState } from '@/components/EmptyState'
import { SeverityBadge } from '@/components/SeverityBadge'
import { Card, SectionTitle, Skeleton, ErrorNote } from '@/components/ui'
import type { AttackPath as AttackPathT } from '@/api/types'

const LEGEND = [
  { c: 'bg-aws', t: 'AWS 노드' },
  { c: 'bg-azure', t: 'Azure 노드' },
  { c: 'bg-red-600', t: '크로스클라우드 엣지(경계 횡단)' },
  { c: 'bg-slate-400', t: '내부 엣지' },
]

// 경로 종류(크로스클라우드 / AWS 단독 / Azure 단독) 판정 — cross_cloud 엣지·노드 클라우드로 도출.
function pathKind(p: AttackPathT): { label: string; cross: boolean } {
  const cross = (p.edges ?? []).some((e) => e.cross_cloud)
  if (cross) return { label: '크로스클라우드', cross: true }
  const clouds = new Set((p.nodes ?? []).map((n) => n.cloud))
  if (clouds.size === 1) return { label: clouds.has('aws') ? 'AWS 단독' : 'Azure 단독', cross: false }
  return { label: '혼합', cross: false }
}

// 위험도순 정렬 키(백엔드 정렬과 무관하게 클라이언트에서 hero 최상단 보장):
// severity 낮을수록(1=Critical) 먼저 → 크로스클라우드 우선 → 노드 많은 순.
function rankKey(p: AttackPathT): [number, number, number] {
  const cross = (p.edges ?? []).some((e) => e.cross_cloud)
  return [p.severity_id, cross ? 0 : 1, -(p.nodes?.length ?? 0)]
}

// 경로 제목 = 진입 노드 → 목표 노드(하드코딩 없이 데이터에서 도출).
function pathTitle(p: AttackPathT): string {
  const ns = p.nodes ?? []
  if (ns.length === 0) return '경로'
  return ns.length === 1 ? ns[0].label : `${ns[0].label} → ${ns[ns.length - 1].label}`
}

export default function AttackPath() {
  const { id } = useParams()
  const list = useAttackPaths()
  const [picked, setPicked] = useState<string | null>(null)

  const paths = useMemo(() => {
    const arr = [...(list.data ?? [])]
    arr.sort((a, b) => {
      const ka = rankKey(a)
      const kb = rankKey(b)
      return ka[0] - kb[0] || ka[1] - kb[1] || ka[2] - kb[2]
    })
    return arr
  }, [list.data])

  if (list.isLoading) return <Skeleton className="h-[520px] w-full rounded-xl" />
  if (list.isError) return <ErrorNote message={(list.error as Error)?.message} />
  if (!paths.length) return <EmptyState title="상관된 attack-path 없음" hint="단일 finding은 목록에서 확인" />

  const activeId = picked ?? id ?? paths[0].attack_path_id
  const active = paths.find((p) => p.attack_path_id === activeId) ?? paths[0]
  const activeKind = pathKind(active)

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">공격 경로</h1>
          <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-bold text-brand">{paths.length}</span>
        </div>
        <p className="mt-0.5 text-sm text-slate-500">
          현재 posture에서 발견된 독립 공격 경로 {paths.length}개 · 위험도순 · finding이 사라지면 경로도 리스트에서 빠짐
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        {/* 좌: 위험도순 경로 리스트 */}
        <div className="space-y-2">
          {paths.map((p, i) => {
            const kind = pathKind(p)
            const on = p.attack_path_id === active.attack_path_id
            return (
              <button
                key={p.attack_path_id}
                onClick={() => setPicked(p.attack_path_id)}
                className={`w-full rounded-xl border p-3 text-left transition ${
                  on ? 'border-brand bg-brand-50 ring-1 ring-brand' : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-bold text-slate-400">#{i + 1}</span>
                  <SeverityBadge id={p.severity_id} />
                  {kind.cross ? (
                    <span className="rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-bold text-red-600">
                      크로스클라우드
                    </span>
                  ) : (
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">
                      {kind.label}
                    </span>
                  )}
                </div>
                <div className="mt-1.5 text-sm font-semibold leading-snug text-slate-800">{pathTitle(p)}</div>
                <div className="mt-1 text-xs text-slate-400">
                  {p.nodes?.length ?? 0}노드 · {p.edges?.length ?? 0}엣지
                </div>
              </button>
            )
          })}
        </div>

        {/* 우: 선택 경로 그래프 + 서사 */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <SeverityBadge id={active.severity_id} />
            {activeKind.cross && (
              <span className="rounded bg-red-50 px-2 py-0.5 text-xs font-bold text-red-600">크로스클라우드</span>
            )}
            <span className="text-sm text-slate-500">
              {active.nodes?.length ?? 0}노드 · {active.edges?.length ?? 0}엣지
            </span>
          </div>

          <AttackPathGraph path={active} />

          {/* 범례 */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
            {LEGEND.map((l) => (
              <span key={l.t} className="flex items-center gap-1.5">
                <span className={`inline-block h-2.5 w-2.5 rounded-full ${l.c}`} />
                {l.t}
              </span>
            ))}
          </div>

          <Card className="p-5">
            <SectionTitle>공격 서사 (Reasoning)</SectionTitle>
            <p className="text-sm leading-relaxed text-slate-700">{active.narrative_text}</p>
          </Card>
        </div>
      </div>
    </div>
  )
}
