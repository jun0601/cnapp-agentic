import { useState, useRef, useEffect, type ReactNode } from 'react'
import { useChat, type ChatRef } from '@/api/queries'

// AI 보안 어시스턴트 — RAG(Titan 임베딩 → pgvector → Bedrock Haiku). 실 지식베이스 근거로 답변.
// "챗봇 탈출"의 얼굴: 사용자가 자연어로 물으면 실제 벡터 검색 + LLM이 근거와 함께 답한다.

interface Msg {
  role: 'user' | 'ai'
  text: string
  refs?: ChatRef[]
  error?: boolean
}

const SUGGESTIONS = [
  '공개된 S3 버킷이 왜 위험하고 어떻게 조치하나요?',
  '과도한 IRSA 권한(s3:*)의 위험과 최소권한 방법은?',
  'KEV 취약점이 뭐고 컨테이너 이미지에 있으면 어떻게 하나요?',
  '평문 Azure 시크릿 노출 시 크로스클라우드 위험은?',
]

// ── 의존성 없는 마크다운-lite 렌더 (헤더/볼드/코드/불릿) — dangerouslySetInnerHTML 미사용(안전) ──
function inline(text: string, key: number): ReactNode {
  // **bold** 와 `code` 를 분해
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return (
    <span key={key}>
      {parts.map((p, i) => {
        if (p.startsWith('**') && p.endsWith('**')) return <strong key={i} className="font-semibold text-slate-900">{p.slice(2, -2)}</strong>
        if (p.startsWith('`') && p.endsWith('`')) return <code key={i} className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[0.85em] text-indigo-600">{p.slice(1, -1)}</code>
        return p
      })}
    </span>
  )
}

function RichText({ text }: { text: string }) {
  const lines = text.split('\n')
  const out: ReactNode[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.startsWith('### ')) out.push(<h4 key={i} className="mt-3 mb-1 text-sm font-bold text-slate-800">{inline(line.slice(4), i)}</h4>)
    else if (line.startsWith('## ')) out.push(<h3 key={i} className="mt-3 mb-1 text-base font-bold text-slate-900">{inline(line.slice(3), i)}</h3>)
    else if (line.startsWith('# ')) out.push(<h2 key={i} className="mt-3 mb-1 text-lg font-bold text-slate-900">{inline(line.slice(2), i)}</h2>)
    else if (/^\s*[-*]\s+/.test(line)) out.push(<div key={i} className="ml-1 flex gap-2"><span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-indigo-400" /><span>{inline(line.replace(/^\s*[-*]\s+/, ''), i)}</span></div>)
    else if (/^\s*\d+\.\s+/.test(line)) out.push(<div key={i} className="ml-1">{inline(line, i)}</div>)
    else if (line.trim() === '') out.push(<div key={i} className="h-2" />)
    else out.push(<p key={i} className="leading-relaxed">{inline(line, i)}</p>)
    i++
  }
  return <div className="space-y-0.5 text-sm text-slate-700">{out}</div>
}

function Bubble({ m }: { m: Msg }) {
  if (m.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2.5 text-sm text-white shadow-sm">{m.text}</div>
      </div>
    )
  }
  return (
    <div className="flex gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-sm shadow-sm">🤖</div>
      <div className="min-w-0 max-w-[85%]">
        <div className={`rounded-2xl rounded-tl-sm border px-4 py-3 shadow-sm ${m.error ? 'border-rose-200 bg-rose-50' : 'border-slate-200 bg-white'}`}>
          {m.error ? <p className="text-sm text-rose-600">{m.text}</p> : <RichText text={m.text} />}
        </div>
        {m.refs && m.refs.length > 0 && (
          <div className="mt-2 space-y-1.5">
            <span className="flex items-center gap-1.5 text-[11px] font-medium text-slate-400">
              <span className="rounded bg-violet-100 px-1.5 py-0.5 font-semibold text-violet-600">pgvector</span>
              코사인 유사도 검색으로 찾은 근거 {m.refs.length}건
            </span>
            <div className="grid gap-1 sm:grid-cols-2">
              {m.refs.map((r, i) => (
                <div key={i} className="rounded-lg border border-indigo-100 bg-indigo-50/40 px-2.5 py-1.5">
                  <span className="font-mono text-[10px] font-semibold text-indigo-600">{r.control}</span>
                  <p className="mt-0.5 line-clamp-1 text-[11px] text-slate-500">{r.snippet}…</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Chat() {
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const chat = useChat()
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, chat.isPending])

  function send(q: string) {
    const question = q.trim()
    if (!question || chat.isPending) return
    setMessages((m) => [...m, { role: 'user', text: question }])
    setInput('')
    chat.mutate(question, {
      onSuccess: (res) => setMessages((m) => [...m, { role: 'ai', text: res.answer, refs: res.refs }]),
      onError: () => setMessages((m) => [...m, { role: 'ai', text: '답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.', error: true }]),
    })
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      {/* 헤더 */}
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 text-xl shadow-md shadow-indigo-200">🤖</div>
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-slate-900">
            AI 보안 어시스턴트
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">RAG · 실 지식베이스</span>
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-1 text-[10px]">
            <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-600">Titan 임베딩</span>
            <span className="text-slate-300">→</span>
            <span className="rounded bg-violet-100 px-1.5 py-0.5 font-semibold text-violet-600">pgvector 코사인 검색</span>
            <span className="text-slate-300">→</span>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-600">Bedrock 답변</span>
          </div>
        </div>
      </div>

      {/* 대화 영역 */}
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto rounded-2xl border border-slate-200 bg-slate-50/50 p-5">
        {messages.length === 0 && !chat.isPending && (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-3xl bg-gradient-to-br from-indigo-500 to-violet-600 text-3xl shadow-lg shadow-indigo-200">🤖</div>
            <h2 className="mt-4 text-lg font-bold text-slate-800">무엇을 도와드릴까요?</h2>
            <p className="mt-1 max-w-sm text-sm text-slate-500">클라우드 보안 findings·조치·위험에 대해 물어보세요. 실제 지식베이스를 검색해 근거와 함께 답합니다.</p>
            <div className="mt-6 grid w-full max-w-lg gap-2 sm:grid-cols-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-xl border border-slate-200 bg-white p-3 text-left text-xs text-slate-600 shadow-sm transition hover:border-indigo-300 hover:bg-indigo-50/40 hover:text-slate-800"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => <Bubble key={i} m={m} />)}

        {chat.isPending && (
          <div className="flex gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-sm shadow-sm">🤖</div>
            <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm border border-slate-200 bg-white px-4 py-3.5 shadow-sm">
              <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-400 [animation-delay:-0.3s]" />
              <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-400 [animation-delay:-0.15s]" />
              <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-400" />
              <span className="ml-1 text-xs text-slate-400">지식베이스 검색 중…</span>
            </div>
          </div>
        )}
      </div>

      {/* 입력 */}
      <form
        onSubmit={(e) => { e.preventDefault(); send(input) }}
        className="mt-4 flex items-end gap-2"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
          rows={1}
          placeholder="보안 질문을 입력하세요… (Enter 전송, Shift+Enter 줄바꿈)"
          className="max-h-32 flex-1 resize-none rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-800 shadow-sm outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
        />
        <button
          type="submit"
          disabled={!input.trim() || chat.isPending}
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <span className="text-lg">↑</span>
        </button>
      </form>
    </div>
  )
}
