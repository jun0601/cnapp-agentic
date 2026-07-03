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
    <div className="flex min-h-screen items-center justify-center bg-slate-900 text-slate-200">
      {error ? (
        <div className="text-center">
          <p className="text-red-400">로그인 처리 실패</p>
          <p className="mt-1 text-xs text-slate-400">{error}</p>
          <button
            onClick={() => navigate('/login', { replace: true })}
            className="mt-4 rounded bg-slate-700 px-4 py-2 text-sm hover:bg-slate-600"
          >
            로그인으로 돌아가기
          </button>
        </div>
      ) : (
        <p className="animate-pulse text-sm">인증 처리 중…</p>
      )}
    </div>
  )
}
