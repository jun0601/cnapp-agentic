import type { FindingsFilter } from '@/api/queries'

const CLOUDS = ['', 'aws', 'azure']
const PILLARS = ['', 'cspm', 'ciem', 'vuln', 'kspm', 'data']
const STATUSES = ['', 'open', 'remediated', 'suppressed']
const SORTS = ['priority', 'severity']

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (v: string) => void
}) {
  return (
    <label className="flex items-center gap-1 text-xs text-slate-500">
      {label}
      <select
        className="rounded border border-slate-300 bg-white px-2 py-1 text-slate-800"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o === '' ? '전체' : o}
          </option>
        ))}
      </select>
    </label>
  )
}

export function PillarFilter({
  filter,
  onChange,
}: {
  filter: FindingsFilter
  onChange: (f: FindingsFilter) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Select label="클라우드" value={filter.cloud ?? ''} options={CLOUDS} onChange={(v) => onChange({ ...filter, cloud: v || undefined })} />
      <Select label="기둥" value={filter.pillar ?? ''} options={PILLARS} onChange={(v) => onChange({ ...filter, pillar: v || undefined })} />
      <Select label="상태" value={filter.status ?? ''} options={STATUSES} onChange={(v) => onChange({ ...filter, status: v || undefined })} />
      <Select label="정렬" value={filter.sort ?? 'priority'} options={SORTS} onChange={(v) => onChange({ ...filter, sort: v })} />
    </div>
  )
}
