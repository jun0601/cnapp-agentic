import { EmptyState } from '@/components/EmptyState'

// 감사로그 뷰어 — 불변 감사로그(S3 Object Lock) 조회. 스텁(Day10).
export default function Audit() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">감사로그</h1>
      <EmptyState title="감사 이벤트 없음" hint="Day10 — 판정·조치 불변 로그 뷰어" />
    </div>
  )
}
