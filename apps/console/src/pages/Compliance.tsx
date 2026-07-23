import { Fragment } from 'react'
import { useCompliance } from '@/api/queries'
import { Card, Skeleton, ErrorNote } from '@/components/ui'
import type { ComplianceControl, ComplianceStatus } from '@/api/view-types'

const STATUS_META: Record<ComplianceStatus, { label: string; cls: string; dot: string }> = {
  pass: { label: '충족', cls: 'text-emerald-700', dot: 'bg-emerald-500' },
  fail: { label: '미충족', cls: 'text-rose-700', dot: 'bg-rose-500' },
  na: { label: '해당없음', cls: 'text-slate-400', dot: 'bg-slate-300' },
}

function scoreColor(score: number) {
  if (score >= 70) return 'text-emerald-600'
  if (score >= 40) return 'text-amber-600'
  return 'text-rose-600'
}

function ControlRow({ c }: { c: ComplianceControl }) {
  const meta = STATUS_META[c.status]
  return (
    <tr className="border-b border-slate-50 last:border-0">
      <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-slate-400">{c.code}</td>
      <td className="px-4 py-2 text-slate-700">{c.title}</td>
      <td className="px-4 py-2">
        {c.mapped_control ? (
          <span className="font-mono text-xs text-slate-400">{c.mapped_control}</span>
        ) : (
          <span className="text-xs text-slate-300">—</span>
        )}
      </td>
      <td className="px-4 py-2 text-center text-xs tabular-nums text-slate-500">{c.findings || ''}</td>
      <td className="px-4 py-2">
        <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${meta.cls}`}>
          <span className={`h-2 w-2 rounded-full ${meta.dot}`} />
          {meta.label}
        </span>
      </td>
    </tr>
  )
}

export default function Compliance() {
  const { data, isLoading, isError, error } = useCompliance()

  if (isLoading)
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  if (isError) return <ErrorNote message={(error as Error)?.message} />
  if (!data) return null

  const all = data.domains.flatMap((d) => d.controls)
  const pass = all.filter((c) => c.status === 'pass').length
  const fail = all.filter((c) => c.status === 'fail').length

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">컴플라이언스</h1>
          <p className="mt-0.5 text-sm text-slate-500">ISMS-P ↔ INTERNAL control 매핑 · 충족률</p>
        </div>
        <button
          onClick={() => window.print()}
          title="브라우저 인쇄 → PDF로 저장"
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
        >
          PDF 내보내기
        </button>
      </div>

      {/* 프레임워크 설명 — '2.5' 같은 번호가 뭔지 처음 보는 사람도 알 수 있게 */}
      <div className="rounded-xl border border-slate-200 bg-slate-50/70 px-4 py-3 text-sm leading-relaxed text-slate-600">
        <span className="font-semibold text-slate-700">ISMS-P</span>
        <span className="text-slate-400"> · 정보보호 및 개인정보보호 관리체계 인증</span> — 국내 정보보호 인증 표준입니다.{' '}
        <code className="rounded bg-white px-1 py-0.5 font-mono text-xs text-slate-500">2.5</code>
        <code className="ml-1 rounded bg-white px-1 py-0.5 font-mono text-xs text-slate-500">2.6.4</code> 같은 번호가 그 인증 기준의{' '}
        <span className="font-medium text-slate-700">통제항목</span>이며, 이 화면은 각 항목을 플랫폼 내부 control에 매핑해{' '}
        <span className="font-medium text-slate-700">실 finding 집계로 충족·미충족을 자동 판정</span>합니다.
      </div>

      {/* 점수 요약 */}
      <Card className="flex flex-wrap items-center gap-6 p-6">
        <div className="text-center">
          <p className={`text-5xl font-bold tabular-nums ${scoreColor(data.score)}`}>{data.score}</p>
          <p className="mt-1 text-xs text-slate-400">충족률 (%)</p>
        </div>
        <div className="h-12 w-px bg-slate-200" />
        <div className="flex gap-6 text-sm">
          <div>
            <p className="text-2xl font-bold tabular-nums text-emerald-600">{pass}</p>
            <p className="text-xs text-slate-400">충족</p>
          </div>
          <div>
            <p className="text-2xl font-bold tabular-nums text-rose-600">{fail}</p>
            <p className="text-xs text-slate-400">미충족</p>
          </div>
        </div>
        <div className="ml-auto text-right text-xs text-slate-400">
          <p className="font-medium text-slate-500">{data.framework}</p>
          <p>생성 {data.generated_at.replace('T', ' ').replace('Z', ' UTC')}</p>
        </div>
      </Card>

      {/* 도메인별 미충족 요약 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {data.domains.map((d) => {
          const f = d.controls.filter((c) => c.status === 'fail').length
          return (
            <Card key={d.code} className="p-3">
              <p className="text-xs font-mono text-slate-400">{d.code}</p>
              <p className="mt-0.5 truncate text-sm font-medium text-slate-700" title={d.name}>
                {d.name}
              </p>
              <p className={`mt-1 text-lg font-bold tabular-nums ${f > 0 ? 'text-rose-600' : 'text-emerald-600'}`}>
                {f > 0 ? `${f} 미충족` : '충족'}
              </p>
            </Card>
          )
        })}
      </div>

      {/* control 표 (도메인 그룹) */}
      <Card className="overflow-hidden">
        <div className="border-b border-slate-100 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
          항목별 상세 (ISMS-P ↔ INTERNAL control 매핑)
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50 text-left text-xs text-slate-400">
              <th className="px-4 py-2 font-medium">항목</th>
              <th className="px-4 py-2 font-medium">기준</th>
              <th className="px-4 py-2 font-medium">매핑 control</th>
              <th className="px-4 py-2 text-center font-medium">finding</th>
              <th className="px-4 py-2 font-medium">상태</th>
            </tr>
          </thead>
          <tbody>
            {data.domains.map((d) => (
              <Fragment key={d.code}>
                <tr className="bg-slate-50/50">
                  <td colSpan={5} className="px-4 py-1.5 text-xs font-semibold text-slate-500">
                    {d.code} · {d.name}
                  </td>
                </tr>
                {d.controls.map((c) => (
                  <ControlRow key={c.code} c={c} />
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
