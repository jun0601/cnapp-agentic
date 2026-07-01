import { useRole } from '@/lib/auth'
import { Card, SectionTitle } from '@/components/ui'
import { EmptyState } from '@/components/EmptyState'

// 자동 조치 카탈로그 MVP 3종(§14). HITL — approver만 승인 가능.
const CATALOG = [
  { id: 's3-block', title: 'S3 Public Access Block 설정', target: 'aws:s3_bucket:member-pii-prod', auto: true },
  { id: 'sg-remove', title: 'SG 0.0.0.0/0 인바운드 제거', target: 'aws:security_group:sg-0product1234', auto: true },
  { id: 'iam-diff', title: 'IAM 최소권한 diff 제안', target: 'aws:iam_role:order-irsa', auto: false },
]

export default function Remediation() {
  const role = useRole()
  const canApprove = role === 'approver'

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-bold">조치 승인 (HITL)</h1>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${canApprove ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
          {role}
        </span>
      </div>

      {!canApprove && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
          현재 <b>viewer</b> — 조치를 승인하려면 approver 권한이 필요합니다. (개발 중엔 헤더 역할 스위처로 전환)
        </p>
      )}

      <SectionTitle>자동 조치 카탈로그 (MVP 3종)</SectionTitle>
      <div className="space-y-2">
        {CATALOG.map((c) => (
          <Card key={c.id} className="flex items-center gap-3 p-4">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-800">{c.title}</p>
              <p className="truncate font-mono text-xs text-slate-400">{c.target}</p>
            </div>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">
              {c.auto ? '자동 실행' : '제안만'}
            </span>
            <button
              disabled={!canApprove}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white enabled:hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
              title={canApprove ? '승인 → Step Functions 실행' : 'approver 권한 필요'}
            >
              승인
            </button>
            <button
              disabled={!canApprove}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm enabled:hover:bg-slate-50 disabled:opacity-40"
            >
              거부
            </button>
          </Card>
        ))}
      </div>

      <EmptyState title="대기 중인 실제 조치 없음" hint="Day9 — Step Functions 승인 경로 연동 시 실데이터 표시" />
    </div>
  )
}
