// Evidence 탭(§15.4, UC0) — "AI가 read-only API를 스스로 호출해 증거를 모으는" 능동조사 장면.
// 프로젝트의 심장(챗봇 탈출 기준). case 단위로 렌더(계약⑦).
import type { Case } from '@/api/types'

export function EvidenceTab({ evidenceCase }: { evidenceCase: Case | null }) {
  if (!evidenceCase) {
    return (
      <div className="rounded-lg border border-dashed bg-white p-6 text-sm text-slate-500">
        이 finding에 연결된 능동조사 case가 없습니다. (escalate된 finding만 Evidence 루프를 돈다 — 트리아지 게이트)
      </div>
    )
  }

  const c = evidenceCase
  return (
    <div className="space-y-5">
      {/* 트리아지 게이트 */}
      {c.triage && (
        <section className="rounded-lg border bg-white p-4">
          <h4 className="text-xs font-semibold uppercase text-slate-400">트리아지 게이트</h4>
          <p className="mt-1 text-sm">
            <span className={`mr-2 rounded px-2 py-0.5 text-xs font-semibold ${c.triage.escalate ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-600'}`}>
              {c.triage.escalate ? 'ESCALATE' : 'HOLD'}
            </span>
            {c.triage.reason}
          </p>
        </section>
      )}

      {/* 가설 */}
      {c.hypotheses && c.hypotheses.length > 0 && (
        <section className="rounded-lg border bg-white p-4">
          <h4 className="text-xs font-semibold uppercase text-slate-400">가설 (Hypothesis)</h4>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
            {c.hypotheses.map((h, i) => (
              <li key={i}>{h}</li>
            ))}
          </ul>
        </section>
      )}

      {/* 증거 — read-only tool 호출 타임라인 (핵심) */}
      <section className="rounded-lg border bg-white p-4">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase text-slate-400">
            능동 수집 증거 — read-only API 호출
          </h4>
          {c.evidence_meta && (
            <span className="text-xs text-slate-500">
              {c.evidence_meta.tool_calls_count}회 호출 · 신뢰도 {Math.round((c.evidence_meta.confidence_score ?? 0) * 100)}% ·{' '}
              <span className="font-semibold text-emerald-600">{c.evidence_meta.verdict}</span>
            </span>
          )}
        </div>
        <ol className="mt-3 space-y-2">
          {(c.evidence ?? []).map((e, i) => (
            <li key={i} className="flex gap-3 rounded border border-slate-100 bg-slate-50 p-2 text-sm">
              <span className="shrink-0 rounded bg-slate-900 px-2 py-0.5 font-mono text-xs text-white">
                {e.tool}
              </span>
              <div className="min-w-0">
                <p className="truncate font-mono text-xs text-slate-400">{e.resource_id}</p>
                <p className="text-slate-700">{e.result_summary}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* 판정 */}
      {c.reasoning && (
        <section className="rounded-lg border bg-white p-4">
          <h4 className="text-xs font-semibold uppercase text-slate-400">판정 (Reasoning)</h4>
          <p className="mt-1 text-sm">
            <span className="mr-2 rounded bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
              {c.reasoning.verdict}
            </span>
            신뢰도 {Math.round((c.reasoning.confidence_score ?? 0) * 100)}%
          </p>
          <p className="mt-2 text-sm leading-relaxed text-slate-700">{c.reasoning.narrative}</p>
          {c.reasoning.rag_refs && (
            <p className="mt-2 flex flex-wrap gap-1 text-xs text-slate-400">
              {c.reasoning.rag_refs.map((r) => (
                <span key={r} className="rounded bg-slate-100 px-1.5 py-0.5">
                  {r}
                </span>
              ))}
            </p>
          )}
        </section>
      )}

      {/* 모델 추적(비용) */}
      {c.model_trace && (
        <section className="rounded-lg border bg-white p-4">
          <h4 className="text-xs font-semibold uppercase text-slate-400">모델 추적 (비용)</h4>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            {c.model_trace.map((m, i) => (
              <span key={i} className="rounded bg-slate-100 px-2 py-0.5">
                {m.stage}: <b>{m.model}</b> ({m.tokens}tok)
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
