import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { completeLogin } from '@/lib/oidc'

// OIDC 콜백(옵션 B) — Cognito Hosted UI가 code와 함께 여기로 리다이렉트.
// completeLogin()이 code↔토큰 교환 후 대시보드로. 실패 시 로그인으로 되돌림.
export default function Callback() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    completeLogin()
      .then(() => navigate('/', { replace: true }))
      .catch((e) => setError(String(e?.message ?? e)))
  }, [navigate])

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-4 text-slate-200">
      {/* 배경 글로우 */}
      <div className="pointer-events-none absolute -top-24 left-1/2 h-72 w-72 -translate-x-1/2 rounded-full bg-brand-600/20 blur-3xl" />

      {error ? (
        <div className="relative w-full max-w-sm rounded-2xl border border-slate-700/60 bg-slate-900/60 p-8 text-center shadow-2xl backdrop-blur">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-rose-500/15 text-2xl">⚠️</div>
          <p className="mt-4 font-semibold text-rose-300">로그인 처리 실패</p>
          <p className="mt-1.5 break-words text-xs text-slate-400">{error}</p>
          <button
            onClick={() => navigate('/login', { replace: true })}
            className="mt-5 w-full rounded-lg bg-slate-700 px-4 py-2.5 text-sm font-medium transition hover:bg-slate-600"
          >
            로그인으로 돌아가기
          </button>
        </div>
      ) : (
        <div className="relative flex flex-col items-center text-center">
          {/* 회전 링 + 방패 로고 */}
          <div className="relative flex h-20 w-20 items-center justify-center">
            <span className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-brand-500 border-r-brand-500/40" />
            <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-600 to-violet-600 text-2xl shadow-glow">
              🛡️
            </span>
          </div>
          <p className="mt-6 text-sm font-medium text-slate-200">보안 인증 처리 중…</p>
          <p className="mt-1 text-xs text-slate-500">Entra ID → Cognito → 토큰 교환</p>
        </div>
      )}
    </div>
  )
}
