import { Link } from 'react-router-dom'
import { useScores, useAttackPaths, useFindings } from '@/api/queries'
import { StatCard } from '@/components/StatCard'
import { FindingCard } from '@/components/FindingCard'
import { EmptyState } from '@/components/EmptyState'
import { Card, SectionTitle, Skeleton, SkeletonRows, ErrorNote } from '@/components/ui'
import { PILLAR_LABEL } from '@/lib/severity'
import type { Finding, Pillar } from '@/api/types'

function ScoreBar({ cloud, score, label }: { cloud: 'aws' | 'azure'; score: number; label: string }) {
  const barColor = cloud === 'aws' ? 'bg-aws' : 'bg-azure'
  const textColor = cloud === 'aws' ? 'text-aws' : 'text-azure'
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className={`text-sm font-semibold uppercase ${textColor}`}>{cloud}</span>
        <span className="text-xs text-slate-400">{label}</span>
      </div>
      <div className="mt-1 flex items-center gap-2">
        <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
          <div className={`h-full rounded-full ${barColor}`} style={{ width: `${score}%` }} />
        </div>
        <span className="w-12 text-right text-lg font-bold tabular-nums">{score}</span>
      </div>
    </div>
  )
}

function PillarBreakdown({ findings }: { findings: Finding[] }) {
  const pillars: Pillar[] = ['cspm', 'ciem', 'vuln', 'kspm', 'data']
  const counts = pillars.map((p) => ({ p, n: findings.filter((f) => f.pillar === p && f.status === 'open').length }))
  const max = Math.max(1, ...counts.map((c) => c.n))
  return (
    <div className="space-y-2">
      {counts.map(({ p, n }) => (
        <div key={p} className="flex items-center gap-2 text-sm">
          <span className="w-16 text-slate-500">{PILLAR_LABEL[p]}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-slate-700" style={{ width: `${(n / max) * 100}%` }} />
          </div>
          <span className="w-6 text-right tabular-nums text-slate-600">{n}</span>
        </div>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const scores = useScores()
  const paths = useAttackPaths()
  const all = useFindings({ sort: 'priority' })

  const findings = all.data ?? []
  const open = findings.filter((f) => f.status === 'open')
  const critical = open.filter((f) => f.severity_id === 1)
  const topFindings = open.slice(0, 5)

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">대시보드</h1>

      {/* KPI — 숫자 리드 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {all.isLoading ? (
          <>
            {Array.from({ length: 4 }).map((_, i) => (
              <Card key={i} className="p-4">
                <Skeleton className="h-4 w-16" />
                <Skeleton className="mt-2 h-8 w-12" />
              </Card>
            ))}
          </>
        ) : (
          <>
            <StatCard label="전체 finding" value={findings.length} />
            <StatCard label="Open" value={open.length} accent="amber" />
            <StatCard label="Critical" value={critical.length} accent="red" hint="severity 1" />
            <StatCard label="공격 경로" value={paths.data?.length ?? 0} accent="red" />
          </>
        )}
      </div>

      {/* 점수 + 기둥 분포 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-2">
          <SectionTitle>Secure Score</SectionTitle>
          {scores.isError ? (
            <ErrorNote />
          ) : scores.data ? (
            <div className="space-y-4">
              <ScoreBar cloud="aws" score={scores.data.aws.secure_score} label={scores.data.aws.label} />
              <ScoreBar cloud="azure" score={scores.data.azure.secure_score} label={scores.data.azure.label} />
            </div>
          ) : (
            <Skeleton className="h-16 w-full" />
          )}
        </Card>
        <Card className="p-5">
          <SectionTitle>기둥별 Open</SectionTitle>
          {all.isLoading ? <Skeleton className="h-28 w-full" /> : <PillarBreakdown findings={findings} />}
        </Card>
      </div>

      {/* attack-path 배너 */}
      <section>
        <SectionTitle>크로스클라우드 attack-path</SectionTitle>
        {paths.isError ? (
          <ErrorNote />
        ) : paths.data && paths.data.length > 0 ? (
          <div className="space-y-2">
            {paths.data.map((p) => (
              <Link
                key={p.attack_path_id}
                to={`/attack-paths/${p.attack_path_id}`}
                className="flex items-center gap-3 rounded-xl border border-red-200 bg-gradient-to-r from-red-50 to-white p-4 transition hover:border-red-300 hover:shadow-sm"
              >
                <span className="text-xl">🛑</span>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-red-700">
                    {p.nodes.length}노드 · {p.edges.length}엣지 공격 경로 (AWS → Azure)
                  </p>
                  <p className="line-clamp-2 text-xs text-slate-600">{p.narrative_text}</p>
                </div>
                <span className="ml-auto shrink-0 text-red-400">→</span>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState title="상관된 attack-path 없음" hint="단일 finding은 목록에서 확인" />
        )}
      </section>

      {/* 상위 finding */}
      <section>
        <SectionTitle>우선순위 상위 finding</SectionTitle>
        <Card className="overflow-hidden">
          {all.isLoading ? (
            <SkeletonRows rows={5} />
          ) : all.isError ? (
            <div className="p-4">
              <ErrorNote />
            </div>
          ) : topFindings.length > 0 ? (
            topFindings.map((f) => <FindingCard key={f.finding_id} f={f} />)
          ) : (
            <EmptyState title="open finding 없음" />
          )}
        </Card>
      </section>
    </div>
  )
}
