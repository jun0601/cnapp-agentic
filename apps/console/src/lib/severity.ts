// severity_id 내부 컨벤션(1=Critical~5=Info, OCSF와 반대) 표시 헬퍼.
import type { SeverityId, Pillar } from '@/api/types'

export const SEVERITY_LABEL: Record<SeverityId, string> = {
  1: 'Critical',
  2: 'High',
  3: 'Medium',
  4: 'Low',
  5: 'Info',
}

export const SEVERITY_CLASS: Record<SeverityId, string> = {
  1: 'bg-sev-1 text-white',
  2: 'bg-sev-2 text-white',
  3: 'bg-sev-3 text-white',
  4: 'bg-sev-4 text-white',
  5: 'bg-sev-5 text-white',
}

export const PILLAR_LABEL: Record<Pillar, string> = {
  cspm: 'CSPM',
  ciem: 'CIEM',
  vuln: '취약점',
  kspm: 'KSPM',
  data: '데이터',
  attack_path: 'Attack-path',
}
