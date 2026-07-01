import { useState } from 'react'
import { useRole } from '@/lib/auth'
import { useFindings } from '@/api/queries'
import { Card, SectionTitle, SkeletonRows, ErrorNote } from '@/components/ui'
import { EmptyState } from '@/components/EmptyState'
import { SeverityBadge } from '@/components/SeverityBadge'
import type { Finding } from '@/api/types'

// 자동 조치 카탈로그 MVP 3종(§14) — control_id로 open finding에 매칭.
const ACTIONS: Record<string, { title: string; mode: 'auto' | 'proposal' }> = {
  'INTERNAL-S3-PUBLIC-001': { title: 'S3 Public Access Block 설정', mode: 'auto' },
  'INTERNAL-SG-OPEN-INGRESS-001': { title: 'SG 0.0.0.0/0 인바운드 제거', mode: 'auto' },
  'INTERNAL-IAM-OVERPRIV-001': { title: 'IAM 최소권한 diff 제안', mode: 'proposal' },
}

type Decision = 'approved' | 'rejected'

function ActionRow({
  f,
  canApprove,
  decision,
  onDecide,
}: {
  f: Finding
  canApprove: boolean
  decision?: Decision
  onDecide: (id: string, d: Decision) => void
}) {
  const a = ACTIONS[f.control_id]
  return (
    <Card className="flex items-center gap-3 p-4">
      <SeverityBadge id={f.severity_id} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-slate-800">{a.title}</p>
        <p className="truncate font-mono text-xs text-slate-400">{f.resource_id}</p>
      </div>
      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">
        {a.mode === 'auto' ? '자동 실행' : '제안만'}
      </span>
      {decision ? (
        <span
          className={`rounded px-2 py-1 text-xs font-medium ${
            decision === 'approved' ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'
          }`}
        >
          {decision === 'approved' ? '승인됨 → SFn 실행' : '거부됨'}
        </span>
      ) : (
        <div className="flex gap-2">
          <button
            disabled={!canApprove}
            onClick={() => onDecide(f.finding_id, 'approved')}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white enabled:hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
            title={canApprove ? '승인 → Step Functions 실행' : 'approver 권한 필요'}
          >
            승인
          </button>
          <button
            disabled={!canApprove}
            onClick={() => onDecide(f.finding_id, 'rejected')}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm enabled:hover:bg-slate-50 disabled:opacity-40"
          >
            거부
          </button>
        </div>
      )}
    </Card>
  )
}

export default function Remediation() {
  const role = useRole()
  const canApprove = role === 'approver'
  const { data, isLoading, isError, error } = useFindings({ status: 'open', sort: 'priority' })
  const [decisions, setDecisions] = useState<Record<string, Decision>>({})

  // 자동 조치 가능한 control을 가진 open finding만 큐에 노출
  const queue = (data ?? []).filter((f) => f.control_id in ACTIONS)

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-bold">조치 승인 (HITL)</h1>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            canApprove ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
          }`}
        >
          {role}
        </span>
      </div>

      {!canApprove && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
          현재 <b>viewer</b> — 조치를 승인/거부하려면 approver 권한이 필요합니다. (개발 중엔 헤더 역할 스위처로 전환)
        </p>
      )}

      <p className="text-sm text-slate-500">
        자동 조치 카탈로그 MVP 3종(S3 Public Access Block · SG 0.0.0.0/0 제거 · IAM 최소권한 diff). 승인 시 Step
        Functions로 실행되고 감사로그에 불변 기록됩니다. Azure findings는 가이드만 제공(자동 실행 없음).
      </p>

      <SectionTitle>대기 중인 조치 ({queue.length})</SectionTitle>
      {isLoading ? (
        <Card className="overflow-hidden">
          <SkeletonRows rows={3} />
        </Card>
      ) : isError ? (
        <ErrorNote message={(error as Error)?.message} />
      ) : queue.length > 0 ? (
        <div className="space-y-2">
          {queue.map((f) => (
            <ActionRow
              key={f.finding_id}
              f={f}
              canApprove={canApprove}
              decision={decisions[f.finding_id]}
              onDecide={(id, d) => setDecisions((prev) => ({ ...prev, [id]: d }))}
            />
          ))}
        </div>
      ) : (
        <EmptyState title="자동 조치 대상 open finding 없음" hint="S3 공개·SG 개방·IAM 과도권한 finding이 여기 큐로 들어옵니다" />
      )}
    </div>
  )
}
