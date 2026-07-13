import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useScores, useAttackPaths, useFindings } from '@/api/queries'
import { StatCard } from '@/components/StatCard'
import { FindingCard } from '@/components/FindingCard'
import { EmptyState } from '@/components/EmptyState'
import { Card, SectionTitle, Skeleton, SkeletonRows, ErrorNote } from '@/components/ui'
import { PILLAR_LABEL, SEVERITY_LABEL } from '@/lib/severity'
import type { Finding, Pillar, SeverityId } from '@/api/types'

// 점수 산출 가중치 — console-backend getScores()와 반드시 동일하게 유지(백엔드 공식의 프론트 재현).
const SCORE_WEIGHT: Record<SeverityId, number> = { 1: 8, 2: 4, 3: 2, 4: 1, 5: 0 }

// 점수 산출 근거 툴팁 — "100 - Σ(open finding 등급별 개수 × 가중치)"를 그 클라우드의 실제
// findings로 계산해 보여준다(백엔드와 동일 데이터·동일 공식 재현, 별도 API 불필요).
function ScoreExplainTooltip({ cloud, score, findings }: { cloud: 'aws' | 'azure'; score: number; findings: Finding[] }) {
  const open = findings.filter((f) => f.cloud === cloud && f.status === 'open')
  const rows = ([1, 2, 3, 4] as SeverityId[]).map((sev) => {
    const n = open.filter((f) => f.severity_id === sev).length
    return { sev, n, weight: SCORE_WEIGHT[sev], sub: n * SCORE_WEIGHT[sev] }
  })
  const penalty = rows.reduce((a, r) => a + r.sub, 0)
  return (
    <div
      role="tooltip"
      className="pointer-events-none absolute right-0 top-full z-20 mt-2 w-72 rounded-xl border border-slate-200 bg-white p-3.5 text-left shadow-xl opacity-0 transition-opacity duration-150 group-hover:pointer-events-auto group-hover:opacity-100"
    >
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">점수 산출 근거</p>
      <p className="mt-1 font-mono text-[11px] text-slate-500">100 − Σ(open finding 개수 × 등급 가중치)</p>
      <div className="mt-2.5 space-y-1">
        {rows.map((r) => (
          <div key={r.sev} className="flex items-center justify-between text-xs">
            <span className="text-slate-500">
              {SEVERITY_LABEL[r.sev]} <span className="text-slate-300">(×{r.weight})</span>
            </span>
            <span className="font-mono tabular-nums text-slate-700">
              {r.n}건 → {r.sub > 0 ? `-${r.sub}` : '0'}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-2.5 flex items-center justify-between border-t border-slate-100 pt-2 text-xs font-semibold">
        <span className="text-slate-600">
          100 − {penalty} (10~100 범위)
        </span>
        <span className="text-slate-900">= {score}</span>
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-slate-400">
        실 RDS의 이 클라우드 open findings를 등급별로 집계한 값 — Security Hub/Defender 자체
        점수가 아니라 우리 findings 데이터로 직접 산출(계정 구독제약으로 대체).
      </p>
    </div>
  )
}

function ScoreBar({ cloud, score, label, findings, delta }: { cloud: 'aws' | 'azure'; score: number; label: string; findings: Finding[]; delta: number }) {
  const grad = cloud === 'aws' ? 'from-amber-400 to-orange-500' : 'from-sky-400 to-blue-600'
  const textColor = cloud === 'aws' ? 'text-aws' : 'text-azure'
  return (
    <div className="group relative">
      <div className="flex items-baseline justify-between">
        <span className={`flex items-center gap-1 text-sm font-bold uppercase tracking-wide ${textColor}`}>
          {cloud}
          <span className="cursor-help text-[10px] font-normal normal-case text-slate-300 group-hover:text-slate-400">ⓘ</span>
        </span>
        <span className="text-xs text-slate-400">{label}</span>
      </div>
      <div className="mt-1.5 flex cursor-help items-center gap-3">
        <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
          <div className={`h-full rounded-full bg-gradient-to-r ${grad} transition-all duration-700`} style={{ width: `${score}%` }} />
        </div>
        <span className="flex w-16 items-center justify-end gap-1">
          {delta !== 0 && (
            <span
              className={`animate-pulse rounded-md px-1 py-0.5 text-[11px] font-bold tabular-nums ${
                delta > 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'
              }`}
            >
              {delta > 0 ? `+${delta}` : delta}
            </span>
          )}
          <span className="text-xl font-bold tabular-nums text-slate-800">{score}</span>
        </span>
      </div>
      <ScoreExplainTooltip cloud={cloud} score={score} findings={findings} />
    </div>
  )
}

const PILLAR_ICON: Record<Pillar, string> = { cspm: '☁️', ciem: '🔑', vuln: '🐛', kspm: '⎈', data: '🗄️', attack_path: '🛑' }

function PillarBreakdown({ findings }: { findings: Finding[] }) {
  const pillars: Pillar[] = ['cspm', 'ciem', 'vuln', 'kspm', 'data']
  const counts = pillars.map((p) => ({ p, n: findings.filter((f) => f.pillar === p && f.status === 'open').length }))
  const max = Math.max(1, ...counts.map((c) => c.n))
  return (
    <div className="space-y-2.5">
      {counts.map(({ p, n }) => (
        <div key={p} className="flex items-center gap-2.5 text-sm">
          <span className="flex w-20 items-center gap-1.5 text-slate-500">
            <span className="text-xs">{PILLAR_ICON[p]}</span>
            {PILLAR_LABEL[p]}
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-gradient-to-r from-slate-600 to-slate-800 transition-all duration-700" style={{ width: `${(n / max) * 100}%` }} />
          </div>
          <span className="w-6 text-right font-semibold tabular-nums text-slate-700">{n}</span>
        </div>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const qc = useQueryClient()
  const scores = useScores()
  const paths = useAttackPaths()
  const all = useFindings({ sort: 'priority' })

  // 점수 변화 델타 — 이전 대비 +N/-N을 6초간 강조(조치→점수↑, 스캐너 켬→점수↓가 눈에 띄게).
  const prevScores = useRef<{ aws: number; azure: number } | null>(null)
  const [delta, setDelta] = useState<{ aws: number; azure: number }>({ aws: 0, azure: 0 })
  useEffect(() => {
    if (!scores.data) return
    const cur = { aws: scores.data.aws.secure_score, azure: scores.data.azure.secure_score }
    const prev = prevScores.current
    prevScores.current = cur
    if (prev && (cur.aws !== prev.aws || cur.azure !== prev.azure)) {
      setDelta({ aws: cur.aws - prev.aws, azure: cur.azure - prev.azure })
      const t = setTimeout(() => setDelta({ aws: 0, azure: 0 }), 6000)
      return () => clearTimeout(t)
    }
  }, [scores.data])

  // 수동 새로고침 — 45초 폴링을 기다리지 않고 findings·scores·attack-paths를 즉시 다시 가져온다
  // (데모 중 Security Hub/Macie를 켜서 새 finding이 들어왔을 때 바로 반영).
  const [refreshing, setRefreshing] = useState(false)
  function refreshAll() {
    setRefreshing(true)
    void qc.invalidateQueries()
    setTimeout(() => setRefreshing(false), 900)
  }

  const findings = all.data ?? []
  const open = findings.filter((f) => f.status === 'open')
  const critical = open.filter((f) => f.severity_id === 1)
  const topFindings = open.slice(0, 5)

  return (
    <div className="space-y-6">
      {/* 히어로 */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">보안 대시보드</h1>
          <p className="mt-0.5 text-sm text-slate-500">멀티클라우드(AWS · Azure) 자산의 위험을 한눈에</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="hidden items-center gap-1.5 rounded-full border border-slate-200/70 bg-white px-3 py-1.5 text-xs text-slate-500 shadow-card sm:flex">
            <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" /> 45초 폴링
          </span>
          <button
            onClick={refreshAll}
            className="flex items-center gap-1.5 rounded-full border border-slate-200/70 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 shadow-card transition hover:border-brand-300 hover:text-brand-700"
            title="findings·점수·공격 경로를 즉시 다시 가져오기"
          >
            <span className={refreshing ? 'inline-block animate-spin' : 'inline-block'}>⟳</span> 새로고침
          </button>
        </div>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {all.isLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="p-4">
              <Skeleton className="h-4 w-16" />
              <Skeleton className="mt-2 h-8 w-12" />
            </Card>
          ))
        ) : (
          <>
            <StatCard label="전체 finding" value={findings.length} icon="📋" />
            <StatCard label="Open" value={open.length} accent="amber" icon="🔓" />
            <StatCard label="Critical" value={critical.length} accent="red" hint="severity 1" icon="🔴" />
            <StatCard label="공격 경로" value={paths.data?.length ?? 0} accent="brand" icon="🛑" />
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
              <ScoreBar cloud="aws" score={scores.data.aws.secure_score} label={scores.data.aws.label} findings={findings} delta={delta.aws} />
              <ScoreBar cloud="azure" score={scores.data.azure.secure_score} label={scores.data.azure.label} findings={findings} delta={delta.azure} />
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
        <SectionTitle>크로스클라우드 Attack-path</SectionTitle>
        {paths.isError ? (
          <ErrorNote />
        ) : paths.data && paths.data.length > 0 ? (
          <div className="space-y-2">
            {paths.data.map((p) => (
              <Link
                key={p.attack_path_id}
                to={`/attack-paths/${p.attack_path_id}`}
                className="group flex items-center gap-4 overflow-hidden rounded-2xl border border-red-200/80 bg-gradient-to-r from-red-50 via-rose-50/50 to-white p-4 shadow-card transition hover:-translate-y-0.5 hover:border-red-300 hover:shadow-cardhover"
              >
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-red-500 to-rose-600 text-xl text-white shadow-sm">🛑</span>
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 text-sm font-bold text-red-700">
                    {p.nodes?.length ?? 0}노드 · {p.edges?.length ?? 0}엣지 공격 경로
                    <span className="rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-semibold text-slate-500">AWS → Azure</span>
                  </p>
                  <p className="mt-0.5 line-clamp-2 text-xs text-slate-600">{p.narrative_text}</p>
                </div>
                <span className="ml-auto shrink-0 text-red-400 transition group-hover:translate-x-0.5">→</span>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState title="상관된 attack-path 없음" hint="단일 finding은 목록에서 확인" />
        )}
      </section>

      {/* 상위 finding */}
      <section>
        <SectionTitle action={<Link to="/findings" className="text-xs font-medium text-brand-600 hover:text-brand-700">전체 보기 →</Link>}>
          우선순위 상위 finding
        </SectionTitle>
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
