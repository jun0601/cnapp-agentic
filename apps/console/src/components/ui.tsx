import type { ReactNode } from 'react'

// 공용 UI 프리미티브 — 카드/스켈레톤/섹션 제목/에러. 디자인 토큰 일관성.

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}>{children}</div>
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">{children}</h2>
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-slate-200/70 ${className}`} />
}

export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="divide-y divide-slate-100">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-3">
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
    <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
      데이터를 불러오지 못했습니다. {message && <span className="text-rose-500">({message})</span>}
    </div>
  )
}
