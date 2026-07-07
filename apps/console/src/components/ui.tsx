import type { ReactNode } from 'react'

// 공용 UI 프리미티브 — 카드/배지/섹션제목/스켈레톤/에러. 디자인 토큰 일관성.

export function Card({ children, className = '', hover = false }: { children: ReactNode; className?: string; hover?: boolean }) {
  return (
    <div
      className={`rounded-2xl border border-slate-200/80 bg-white shadow-card ${hover ? 'transition duration-200 hover:-translate-y-0.5 hover:shadow-cardhover' : ''} ${className}`}
    >
      {children}
    </div>
  )
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">{children}</h2>
      {action}
    </div>
  )
}

type Tone = 'slate' | 'brand' | 'red' | 'amber' | 'emerald' | 'aws' | 'azure'
const TONE: Record<Tone, string> = {
  slate: 'bg-slate-100 text-slate-600',
  brand: 'bg-brand-50 text-brand-700',
  red: 'bg-red-50 text-red-600',
  amber: 'bg-amber-50 text-amber-700',
  emerald: 'bg-emerald-50 text-emerald-700',
  aws: 'bg-orange-50 text-orange-600',
  azure: 'bg-sky-50 text-sky-700',
}
export function Badge({ children, tone = 'slate', className = '' }: { children: ReactNode; tone?: Tone; className?: string }) {
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${TONE[tone]} ${className}`}>{children}</span>
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-slate-200/70 ${className}`} />
}

export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="divide-y divide-slate-100">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-3.5">
          <Skeleton className="h-5 w-14" />
          <Skeleton className="h-4 flex-1" />
          <Skeleton className="h-5 w-16" />
        </div>
      ))}
    </div>
  )
}

export function ErrorNote({ message }: { message?: string }) {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
      <span>⚠️</span>
      <span>데이터를 불러오지 못했습니다. {message && <span className="text-rose-500">({message})</span>}</span>
    </div>
  )
}
