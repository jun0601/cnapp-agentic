import { useNavigate, useSearchParams } from 'react-router-dom'
import { IS_MOCK, setRole, getRole, type Role } from '@/lib/auth'
import { oidcConfigured, beginLogin } from '@/lib/oidc'

// SSO 로그인 — 옵션 B: SPA가 Cognito Hosted UI로 직접 OIDC(PKCE).
// 실환경(OIDC 구성 시): 버튼 → beginLogin()이 Hosted UI로 리다이렉트 → Entra → /callback.
// 목업/개발: "로그인" = 역할 선택 후 대시보드로.

const SSO_STEPS = [
  { n: '1', t: 'Microsoft Entra ID', d: '조직 계정으로 인증 (IdP)' },
  { n: '2', t: 'Amazon Cognito', d: 'SAML → User Pool, custom:groups(GUID) 매핑' },
  { n: '3', t: 'SPA (PKCE)', d: 'ID 토큰 → Authorization: Bearer로 백엔드에' },
]

export default function Login() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const sessionExpired = params.get('expired') === '1' // App 가드가 세션 만료 감지 시 붙임
  const realSso = !IS_MOCK && oidcConfigured()

  function loginAs(role: Role) {
    if (realSso) {
      void beginLogin() // Hosted UI로 리다이렉트(역할은 로그인 후 토큰에서 판정)
      return
    }
    if (IS_MOCK) setRole(role)
    navigate('/')
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-4">
      {/* 배경 글로우 */}
      <div className="pointer-events-none absolute -top-32 left-1/4 h-80 w-80 rounded-full bg-brand-600/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-32 right-1/4 h-80 w-80 rounded-full bg-violet-600/15 blur-3xl" />

      <div className="relative w-full max-w-md animate-fade-up">
        {/* 브랜드 로고(카드 밖·상단) */}
        <div className="mb-6 flex flex-col items-center text-center">
          <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-600 to-violet-600 text-3xl shadow-glow">
            🛡️
          </span>
          <h1 className="mt-4 text-2xl font-bold tracking-tight text-white">CNAPP 관제</h1>
          <p className="mt-1 text-sm text-slate-400">에이전틱 AI 기반 멀티클라우드 보안 플랫폼</p>
          {/* 멀티클라우드 신뢰 배지 */}
          <div className="mt-3 flex items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs font-medium text-amber-300">☁️ AWS</span>
            <span className="text-slate-600">+</span>
            <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs font-medium text-sky-300">⊞ Azure Entra</span>
          </div>
        </div>

        <div className="rounded-2xl border border-white/10 bg-white p-8 shadow-2xl">
          {sessionExpired && (
            <div className="mb-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-800">
              <span className="mt-0.5">⏱️</span>
              <span>세션이 만료되었습니다. 보안을 위해 다시 로그인해 주세요.</span>
            </div>
          )}
          {/* 로그인 버튼 — 실환경에선 IdP 리다이렉트. 목업에선 기본 역할(VITE_MOCK_ROLE)로 입장. */}
          <button
            onClick={() => loginAs(getRole())}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-azure to-sky-600 px-4 py-3 font-semibold text-white shadow-lg shadow-sky-600/20 transition hover:brightness-110 active:scale-[0.99]"
          >
            <span className="text-lg">⊞</span> Microsoft Entra ID로 로그인
          </button>
          {IS_MOCK && (
            <p className="mt-1.5 text-center text-xs text-slate-400">
              목업: 기본 역할({getRole()})로 입장 — 아래에서 역할을 골라 입장할 수도 있습니다
            </p>
          )}

          {/* SSO 흐름 안내 */}
          <div className="mt-6">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">SSO 인증 흐름</p>
            <ol className="mt-2 space-y-2">
              {SSO_STEPS.map((s) => (
                <li key={s.n} className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
                    {s.n}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-slate-700">{s.t}</p>
                    <p className="text-xs text-slate-400">{s.d}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>

          {/* 개발용 역할 선택 */}
          {IS_MOCK && (
            <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-3">
              <p className="text-xs font-medium text-amber-700">목업 모드 — 역할을 골라 로그인</p>
              <div className="mt-2 flex gap-2">
                <button
                  onClick={() => loginAs('viewer')}
                  className="flex-1 rounded border border-amber-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-amber-100"
                >
                  viewer로 입장
                </button>
                <button
                  onClick={() => loginAs('approver')}
                  className="flex-1 rounded border border-amber-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-amber-100"
                >
                  approver로 입장
                </button>
              </div>
            </div>
          )}
        </div>
        <p className="mt-4 text-center text-xs text-slate-400">
          read-only first · 모든 조치는 승인(HITL) 경로로만 · 감사로그 불변 기록
        </p>
      </div>
    </div>
  )
}
