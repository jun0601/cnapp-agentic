import { EmptyState } from '@/components/EmptyState'

// 컴플라이언스 리포트(UC5) — 보너스 우선순위(§14). 스텁.
export default function Compliance() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">컴플라이언스 (ISMS-P)</h1>
      <EmptyState title="리포트 미구현" hint="보너스 — PDF 내보내기(UC5)는 후순위" />
    </div>
  )
}
