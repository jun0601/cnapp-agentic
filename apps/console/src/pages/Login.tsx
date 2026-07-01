import { Link } from 'react-router-dom'

// SSO 로그인(Entra→Cognito→ALB authenticate-cognito) 진입점 — 스텁.
// 실환경에선 ALB가 미인증 요청을 IdP로 리다이렉트하므로 이 화면은 목업/개발용.
export default function Login() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50">
      <h1 className="text-2xl font-bold">CNAPP 관제</h1>
      <p className="text-sm text-slate-500">Microsoft Entra ID SSO (Cognito 경유)</p>
      <Link to="/" className="rounded bg-slate-900 px-4 py-2 text-sm text-white">
        (목업) 로그인하고 대시보드로
      </Link>
    </div>
  )
}
