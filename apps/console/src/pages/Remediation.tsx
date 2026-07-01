import { canApprove } from '@/lib/auth'
import { EmptyState } from '@/components/EmptyState'

// 조치 승인(UC4, HITL) — 스텁. Day9에 SFn 연동·RBAC 2역할 적용(§13).
export default function Remediation() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">조치 승인 (HITL)</h1>
      <p className="text-sm text-slate-500">
        현재 역할: <b>{canApprove() ? 'approver' : 'viewer'}</b> · 자동 조치 MVP 3종(S3 block · SG 제거 · IAM diff)
      </p>
      <EmptyState title="대기 중인 조치 없음" hint="Day9 — Step Functions 승인 경로 연동 예정" />
    </div>
  )
}
