import { useParams } from 'react-router-dom'
import { useAttackPaths, useAttackPath } from '@/api/queries'
import { AttackPathGraph } from '@/components/AttackPathGraph'
import { EmptyState } from '@/components/EmptyState'
import { SeverityBadge } from '@/components/SeverityBadge'

export default function AttackPath() {
  const { id } = useParams()
  const list = useAttackPaths()
  // :id 없으면 첫 골든 경로로 폴백
  const resolvedId = id ?? list.data?.[0]?.attack_path_id
  const { data: path, isLoading } = useAttackPath(resolvedId)

  if (isLoading || list.isLoading) return <p className="text-sm text-slate-500">불러오는 중…</p>
  if (!path) return <EmptyState title="상관된 attack-path 없음" hint="단일 finding은 목록에서 확인" />

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-bold">Attack-path</h1>
        <SeverityBadge id={path.severity_id} />
        <span className="text-xs text-slate-400">
          {path.nodes.length}노드 · {path.edges.length}엣지
        </span>
      </div>

      <AttackPathGraph path={path} />

      <section className="rounded-lg border bg-white p-5">
        <h2 className="text-xs font-semibold uppercase text-slate-400">공격 서사 (Reasoning)</h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-700">{path.narrative_text}</p>
      </section>
    </div>
  )
}
