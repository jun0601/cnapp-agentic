import type { SeverityId } from '@/api/types'
import { SEVERITY_CLASS, SEVERITY_LABEL } from '@/lib/severity'

export function SeverityBadge({ id }: { id: SeverityId }) {
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${SEVERITY_CLASS[id]}`}>
      {SEVERITY_LABEL[id]}
    </span>
  )
}
