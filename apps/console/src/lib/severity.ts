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

// 리터럴 클래스 맵(Tailwind JIT가 동적 문자열은 못 잡으므로 리터럴로 고정).
export const SEVERITY_DOT: Record<SeverityId, string> = {
  1: 'bg-sev-1',
  2: 'bg-sev-2',
  3: 'bg-sev-3',
  4: 'bg-sev-4',
  5: 'bg-sev-5',
}

export const PILLAR_LABEL: Record<Pillar, string> = {
  cspm: 'CSPM',
  ciem: 'CIEM',
  vuln: 'VULN',
  kspm: 'KSPM',
  data: 'DSPM',
  attack_path: 'ATTACK-PATH',
}
