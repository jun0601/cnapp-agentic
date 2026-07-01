import { useState } from 'react'
import { useAudit } from '@/api/queries'
import { Card, SkeletonRows, ErrorNote } from '@/components/ui'
import { EmptyState } from '@/components/EmptyState'
import type { AuditAction } from '@/api/view-types'

const ACTION_META: Record<AuditAction, { label: string; cls: string }> = {
  approve: { label: '승인', cls: 'bg-emerald-100 text-emerald-700' },
  reject: { label: '거부', cls: 'bg-rose-100 text-rose-700' },
  verdict: { label: '판정', cls: 'bg-indigo-100 text-indigo-700' },
  scan: { label: '스캔', cls: 'bg-slate-100 text-slate-600' },
  view: { label: '조회', cls: 'bg-slate-100 text-slate-500' },
  login: { label: '로그인', cls: 'bg-sky-100 text-sky-700' },
}

const ROLE_CLS: Record<string, string> = {
  approver: 'text-emerald-600',
  viewer: 'text-slate-500',
  system: 'text-indigo-500',
}

function fmt(ts: string) {
  return ts.replace('T', ' ').replace('Z', ' UTC')
}

export default function Audit() {
  const { data, isLoading, isError, error } = useAudit()
  const [action, setAction] = useState<AuditAction | 'all'>('all')

  const rows = (data ?? []).filter((e) => action === 'all' || e.action === action)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">감사로그</h1>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">🔒 불변 (S3 Object Lock)</span>
      </div>

      <p className="text-sm text-slate-500">
        모든 판정·조치·스캔·인증을 시간순으로 불변 기록합니다. (실데이터: Object Lock S3에서 조회)
      </p>

      {/* 액션 필터 */}
      <div className="flex flex-wrap gap-1.5 text-xs">
        {(['all', 'approve', 'reject', 'verdict', 'scan', 'login', 'view'] as const).map((a) => (
          <button
            key={a}
            onClick={() => setAction(a)}
            className={`rounded-full px-3 py-1 ${
              action === a ? 'bg-slate-900 text-white' : 'bg-white text-slate-600 hover:bg-slate-100'
            } border border-slate-200`}
          >
            {a === 'all' ? '전체' : ACTION_META[a].label}
          </button>
        ))}
      </div>

      <Card className="overflow-hidden">
        {isLoading ? (
          <SkeletonRows rows={8} />
        ) : isError ? (
          <div className="p-4">
            <ErrorNote message={(error as Error)?.message} />
          </div>
        ) : rows.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50 text-left text-xs text-slate-400">
                <th className="px-4 py-2 font-medium">시각</th>
                <th className="px-4 py-2 font-medium">행위자</th>
                <th className="px-4 py-2 font-medium">액션</th>
                <th className="px-4 py-2 font-medium">대상 / 결과</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50">
                  <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-slate-400">{fmt(e.ts)}</td>
                  <td className="whitespace-nowrap px-4 py-2.5">
                    <span className={`font-medium ${ROLE_CLS[e.role] ?? 'text-slate-600'}`}>{e.actor}</span>
                    <span className="ml-1 text-xs text-slate-400">({e.role})</span>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${ACTION_META[e.action].cls}`}>
                      {ACTION_META[e.action].label}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <p className="font-mono text-xs text-slate-400">{e.target}</p>
                    <p className="text-slate-700">{e.result}</p>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState title="해당 액션의 감사 이벤트 없음" />
        )}
      </Card>
    </div>
  )
}
