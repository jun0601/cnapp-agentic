import { useState } from 'react'
import { useRole } from '@/lib/auth'
import { useFindings, useRemediationDecision } from '@/api/queries'
import { Card, SectionTitle, SkeletonRows, ErrorNote } from '@/components/ui'
import { EmptyState } from '@/components/EmptyState'
import { SeverityBadge } from '@/components/SeverityBadge'
import type { Finding } from '@/api/types'

// 자동 조치 카탈로그(§14) — control_id로 open finding에 매칭. 승인 시 실 Step Functions 실행.
const ACTIONS: Record<string, { title: string; mode: 'auto' | 'proposal' }> = {
  'INTERNAL-S3-NOENCRYPT-001': { title: 'S3 서버측 암호화(SSE-S3) 활성화', mode: 'auto' },
  'INTERNAL-ECR-SCAN-DISABLED-001': { title: 'ECR 이미지 스캔(scan-on-push) 활성화', mode: 'auto' },
  'INTERNAL-S3-PUBLIC-001': { title: 'S3 Public Access Block 설정', mode: 'auto' },
  'INTERNAL-SG-OPEN-INGRESS-001': { title: 'SG 0.0.0.0/0 인바운드 제거', mode: 'auto' },
  'INTERNAL-IAM-OVERPRIV-001': { title: 'IAM 최소권한 diff 제안', mode: 'proposal' },
}

type Decision = 'approved' | 'rejected'

function ActionRow({
  f,
  canApprove,
  decision,
  pending,
  onDecide,
}: {
  f: Finding
  canApprove: boolean
  decision?: Decision
  pending?: boolean
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
      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
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
            disabled={!canApprove || pending}
            onClick={() => onDecide(f.finding_id, 'approved')}
            className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm enabled:hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-40"
            title={canApprove ? '승인 → Step Functions 실행' : 'approver 권한 필요'}
          >
            {pending ? '처리 중…' : '승인'}
          </button>
          <button
            disabled={!canApprove || pending}
            onClick={() => onDecide(f.finding_id, 'rejected')}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 enabled:hover:bg-slate-50 disabled:opacity-40"
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
  const decide = useRemediationDecision()
  const [decisions, setDecisions] = useState<Record<string, Decision>>({})
  const [actionError, setActionError] = useState<string | null>(null)

  // 자동 조치 가능한 control을 가진 open finding만 큐에 노출
  const queue = (data ?? []).filter((f) => f.control_id in ACTIONS)

  // 승인/거부 → 백엔드 POST /remediations/:id/{approve,reject} → 성공 시 UI 상태 갱신.
  function handleDecide(id: string, d: Decision) {
    setActionError(null)
    decide.mutate(
      { id, action: d === 'approved' ? 'approve' : 'reject' },
      {
        onSuccess: () => setDecisions((prev) => ({ ...prev, [id]: d })),
        onError: (e) => setActionError((e as Error)?.message ?? '조치 요청 실패'),
      },
    )
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">조치 승인 (HITL)</h1>
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
              canApprove ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
            }`}
          >
            {role}
          </span>
        </div>
        <p className="mt-0.5 text-sm text-slate-500">승인 시 Step Functions 실행 · 감사로그 불변 기록 (read-only first)</p>
      </div>

      {!canApprove && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
          현재 <b>viewer</b> — 조치를 승인/거부하려면 approver 권한이 필요합니다. (개발 중엔 헤더 역할 스위처로 전환)
        </p>
      )}

      {actionError && (
        <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          조치 요청 실패: {actionError}
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
              pending={decide.isPending && decide.variables?.id === f.finding_id}
              onDecide={handleDecide}
            />
          ))}
        </div>
      ) : (
        <EmptyState title="자동 조치 대상 open finding 없음" hint="S3 공개·SG 개방·IAM 과도권한 finding이 여기 큐로 들어옵니다" />
      )}
    </div>
  )
}
