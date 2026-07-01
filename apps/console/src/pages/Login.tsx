import { useNavigate } from 'react-router-dom'
import { IS_MOCK, setRole, getRole, type Role } from '@/lib/auth'

// SSO 로그인(Entra→Cognito→ALB authenticate-cognito) 진입점.
// 실환경: ALB가 미인증 요청을 IdP로 리다이렉트하므로 이 화면은 목업/개발용.
// 목업: "로그인" = 역할 선택 후 대시보드로. (실데이터는 백엔드가 custom:groups로 판정)

const SSO_STEPS = [
  { n: '1', t: 'Microsoft Entra ID', d: '조직 계정으로 인증 (IdP)' },
  { n: '2', t: 'Amazon Cognito', d: 'SAML → User Pool, custom:groups 매핑' },
  { n: '3', t: 'ALB authenticate-cognito', d: 'x-amzn-oidc-data JWT를 백엔드로' },
]

export default function Login() {
  const navigate = useNavigate()

  function loginAs(role: Role) {
    if (IS_MOCK) setRole(role)
    navigate('/')
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-4">
      <div className="w-full max-w-md">
        <div className="rounded-2xl border border-slate-700/50 bg-white p-8 shadow-2xl">
          {/* 로고 + 타이틀 */}
          <div className="flex flex-col items-center text-center">
            <img src="/favicon.svg" alt="" className="h-14 w-14" />
            <h1 className="mt-3 text-xl font-bold text-slate-900">CNAPP 관제</h1>
            <p className="mt-1 text-sm text-slate-500">멀티클라우드 보안 관제 플랫폼</p>
          </div>

          {/* 로그인 버튼 — 실환경에선 IdP 리다이렉트. 목업에선 기본 역할(VITE_MOCK_ROLE)로 입장. */}
          <button
            onClick={() => loginAs(getRole())}
            className="mt-7 flex w-full items-center justify-center gap-2 rounded-lg bg-azure px-4 py-3 font-medium text-white transition hover:brightness-110"
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
