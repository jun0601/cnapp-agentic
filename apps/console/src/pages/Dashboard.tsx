import { Link } from 'react-router-dom'
import { useScores, useAttackPaths, useFindings } from '@/api/queries'
import { ScoreCard } from '@/components/ScoreCard'
import { FindingCard } from '@/components/FindingCard'
import { EmptyState } from '@/components/EmptyState'

export default function Dashboard() {
  const scores = useScores()
  const paths = useAttackPaths()
  const findings = useFindings({ sort: 'priority', status: 'open' })

  const topFindings = (findings.data ?? []).slice(0, 5)

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">대시보드</h1>

      {/* 점수 — AWS 크게 / Azure 보조(§2.0) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {scores.data && (
          <>
            <div className="sm:col-span-2">
              <ScoreCard cloud="aws" score={scores.data.aws.secure_score} label={scores.data.aws.label} emphasis />
            </div>
            <ScoreCard cloud="azure" score={scores.data.azure.secure_score} label={scores.data.azure.label} />
          </>
        )}
      </div>

      {/* attack-path 배너 */}
      <section>
        <h2 className="mb-2 text-sm font-semibold text-slate-500">크로스클라우드 attack-path</h2>
        {paths.data && paths.data.length > 0 ? (
          <div className="space-y-2">
            {paths.data.map((p) => (
              <Link
                key={p.attack_path_id}
                to={`/attack-paths/${p.attack_path_id}`}
                className="block rounded-lg border border-red-200 bg-red-50 p-4 hover:bg-red-100"
              >
                <p className="text-sm font-semibold text-red-700">
                  ⚠ {p.nodes.length}노드 · {p.edges.length}엣지 공격 경로 (AWS→Azure)
                </p>
                <p className="mt-1 line-clamp-2 text-xs text-slate-600">{p.narrative_text}</p>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState title="상관된 attack-path 없음" hint="단일 finding은 목록에서 확인" />
        )}
      </section>

      {/* 상위 finding */}
      <section>
        <h2 className="mb-2 text-sm font-semibold text-slate-500">우선순위 상위 finding</h2>
        <div className="overflow-hidden rounded-lg border">
          {topFindings.length > 0 ? (
            topFindings.map((f) => <FindingCard key={f.finding_id} f={f} />)
          ) : (
            <EmptyState title="open finding 없음" />
          )}
        </div>
      </section>
    </div>
  )
}
