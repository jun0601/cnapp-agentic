import { useParams } from 'react-router-dom'
import { useAttackPaths, useAttackPath } from '@/api/queries'
import { AttackPathGraph } from '@/components/AttackPathGraph'
import { EmptyState } from '@/components/EmptyState'
import { SeverityBadge } from '@/components/SeverityBadge'
import { Card, SectionTitle, Skeleton, ErrorNote } from '@/components/ui'

const LEGEND = [
  { c: 'bg-aws', t: 'AWS 노드' },
  { c: 'bg-azure', t: 'Azure 노드' },
  { c: 'bg-red-600', t: '크로스클라우드 엣지(경계 횡단)' },
  { c: 'bg-slate-400', t: '내부 엣지' },
]

export default function AttackPath() {
  const { id } = useParams()
  const list = useAttackPaths()
  // :id 없으면 첫 골든 경로로 폴백
  const resolvedId = id ?? list.data?.[0]?.attack_path_id
  const { data: path, isLoading, isError, error } = useAttackPath(resolvedId)

  if (isLoading || list.isLoading) return <Skeleton className="h-[520px] w-full rounded-xl" />
  if (isError || list.isError) return <ErrorNote message={(error as Error)?.message} />
  if (!path) return <EmptyState title="상관된 attack-path 없음" hint="단일 finding은 목록에서 확인" />

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">크로스클라우드 Attack-path</h1>
          <SeverityBadge id={path.severity_id} />
        </div>
        <p className="mt-0.5 text-sm text-slate-500">
          {path.nodes?.length ?? 0}노드 · {path.edges?.length ?? 0}엣지 · AWS 워크로드 침해 → Azure Entra 신원 장악
        </p>
      </div>

      <AttackPathGraph path={path} />

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
        <p className="text-sm leading-relaxed text-slate-700">{path.narrative_text}</p>
      </Card>
    </div>
  )
}
