// Evidence 탭(§15.4, UC0) — "AI가 read-only API를 스스로 호출해 증거를 모으는" 능동조사 장면.
// 프로젝트의 심장(챗봇 탈출 기준). case 단위로 렌더(계약⑦).
import type { Case } from '@/api/types'
import { Card, Badge } from './ui'

export function EvidenceTab({ evidenceCase }: { evidenceCase: Case | null }) {
  if (!evidenceCase) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white/60 p-10 text-center">
        <span className="text-3xl">🔎</span>
        <p className="mt-3 text-sm font-medium text-slate-600">연결된 능동조사 case가 없습니다</p>
        <p className="mt-1 max-w-sm text-xs text-slate-400">escalate된 finding만 Evidence 루프를 돕니다 (트리아지 게이트로 비용 통제).</p>
      </div>
    )
  }

  const c = evidenceCase
  const verdict = c.evidence_meta?.verdict ?? c.reasoning?.verdict ?? '—'
  const confidence = Math.round((c.evidence_meta?.confidence_score ?? c.reasoning?.confidence_score ?? 0) * 100)
  const isConfirmed = /confirm/i.test(verdict)
  const vTone = isConfirmed ? 'from-rose-500 to-red-600' : 'from-slate-500 to-slate-600'

  return (
    <div className="space-y-4">
      {/* 판정 히어로 — AI 능동조사 결과 */}
      <div className={`relative overflow-hidden rounded-2xl bg-gradient-to-br ${vTone} p-5 text-white shadow-lg`}>
        <div className="relative z-10 flex items-center gap-4">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/20 text-2xl backdrop-blur">🤖</span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium uppercase tracking-wider text-white/70">AI 능동조사 판정</p>
            <p className="text-2xl font-bold">{verdict}</p>
          </div>
          <div className="hidden text-right sm:block">
            <p className="text-3xl font-bold tabular-nums">{confidence}%</p>
            <p className="text-xs text-white/70">신뢰도</p>
          </div>
        </div>
        <p className="relative z-10 mt-3 text-sm text-white/90">
          AI 에이전트가 <b>{c.evidence_meta?.tool_calls_count ?? c.evidence?.length ?? 0}회</b> read-only API를 <b>스스로 호출</b>해 증거를 수집하고 판정했습니다.
        </p>
        <div className="pointer-events-none absolute -right-6 -top-6 h-28 w-28 rounded-full bg-white/10" />
      </div>

      {/* 조사 흐름: 트리아지 → 가설 → 증거 → 판정 */}
      {c.triage && (
        <Card className="p-4">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">① 트리아지 게이트</h4>
          <p className="mt-2 flex items-center gap-2 text-sm text-slate-700">
            <Badge tone={c.triage.escalate ? 'red' : 'slate'}>{c.triage.escalate ? 'ESCALATE' : 'HOLD'}</Badge>
            {c.triage.reason}
          </p>
        </Card>
      )}

      {c.hypotheses && c.hypotheses.length > 0 && (
        <Card className="p-4">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">② 가설 (Hypothesis)</h4>
          <ul className="mt-2 space-y-1.5 text-sm text-slate-700">
            {c.hypotheses.map((h, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-brand-400" />
                {h}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* 증거 — tool 호출 타임라인 (핵심) */}
      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">③ 능동 수집 증거 · read-only API 호출</h4>
          {c.evidence_meta && (
            <span className="text-xs text-slate-500">
              {c.evidence_meta.tool_calls_count}회 호출 · 신뢰도 {Math.round((c.evidence_meta.confidence_score ?? 0) * 100)}%
            </span>
          )}
        </div>
        <ol className="relative mt-4 space-y-3 border-l-2 border-slate-100 pl-5">
          {(c.evidence ?? []).map((e, i) => (
            <li key={i} className="relative">
              <span className="absolute -left-[26px] flex h-5 w-5 items-center justify-center rounded-full bg-brand-600 text-[10px] font-bold text-white ring-4 ring-white">
                {i + 1}
              </span>
              <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
                <div className="flex items-center gap-2">
                  <code className="rounded-md bg-slate-900 px-2 py-0.5 font-mono text-[11px] text-emerald-300">{e.tool}</code>
                  <span className="truncate font-mono text-xs text-slate-400">{e.resource_id}</span>
                </div>
                <p className="mt-1.5 text-sm text-slate-700">{e.result_summary}</p>
              </div>
            </li>
          ))}
        </ol>
      </Card>

      {/* 판정 내러티브 */}
      {c.reasoning && (
        <Card className="p-4">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">④ 판정 (Reasoning)</h4>
          <p className="mt-2 flex items-center gap-2 text-sm">
            <Badge tone={isConfirmed ? 'red' : 'emerald'}>{c.reasoning.verdict}</Badge>
            <span className="text-slate-500">신뢰도 {confidence}%</span>
          </p>
          <p className="mt-2 text-sm leading-relaxed text-slate-700">{c.reasoning.narrative}</p>
          {c.reasoning.rag_refs && c.reasoning.rag_refs.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-slate-400">지식베이스 근거</span>
              {c.reasoning.rag_refs.map((r) => (
                <span key={r} className="rounded-full border border-indigo-100 bg-indigo-50 px-2 py-0.5 font-mono text-[10px] text-indigo-600">{r}</span>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* 모델 추적(비용 관측) */}
      {c.model_trace && c.model_trace.length > 0 && (
        <Card className="p-4">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">모델 추적 · 토큰(비용)</h4>
          <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
            {c.model_trace.map((m, i) => (
              <span key={i} className="rounded-lg bg-slate-100 px-2 py-1 text-slate-600">
                {m.stage}: <b className="text-slate-800">{m.model}</b> · {m.tokens}tok
              </span>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
