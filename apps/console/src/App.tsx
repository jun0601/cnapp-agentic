import { NavLink, Outlet, Navigate, useLocation } from 'react-router-dom'
import { IS_MOCK, useRole, setRole, needsLogin, type Role } from '@/lib/auth'
import { userEmail, logout, isAuthenticated } from '@/lib/oidc'

const NAV = [
  { to: '/', label: '대시보드', end: true },
  { to: '/findings', label: 'Findings' },
  { to: '/attack-paths', label: 'Attack-path' },
  { to: '/chat', label: 'AI 챗' },
  { to: '/system', label: 'AI·시스템' },
  { to: '/remediation', label: '조치' },
  { to: '/compliance', label: '컴플라이언스' },
  { to: '/audit', label: '감사로그' },
]

// 개발용 역할 스위처(목업 전용) — 실데이터에선 백엔드가 역할을 판정하므로 숨김.
function RoleSwitcher() {
  const role = useRole()
  if (!IS_MOCK) return null
  return (
    <label className="flex items-center gap-1 text-xs text-slate-500">
      <span className="hidden sm:inline">역할</span>
      <select
        value={role}
        onChange={(e) => setRole(e.target.value as Role)}
        className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-slate-700 shadow-sm outline-none focus:border-brand-400"
        title="개발용 역할 전환 (실데이터에선 Cognito custom:groups로 판정)"
      >
        <option value="viewer">viewer</option>
        <option value="approver">approver</option>
      </select>
    </label>
  )
}

// 실데이터(SSO) 로그인 후 헤더 우측 사용자 메뉴 — 이메일·역할·로그아웃.
function UserMenu() {
  const role = useRole()
  const email = userEmail()
  return (
    <div className="flex items-center gap-2.5">
      <div className="hidden flex-col items-end leading-tight sm:flex">
        <span className="max-w-[180px] truncate text-xs font-medium text-slate-700" title={email ?? ''}>
          {email ?? '사용자'}
        </span>
        <span
          className={`text-[10px] font-semibold uppercase tracking-wide ${role === 'approver' ? 'text-emerald-600' : 'text-slate-400'}`}
        >
          {role}
        </span>
      </div>
      <button
        onClick={() => logout()}
        className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
      >
        로그아웃
      </button>
    </div>
  )
}

export default function App() {
  const location = useLocation()
  // 실환경(옵션 B): 미인증이면 로그인 화면으로. 목업은 항상 통과(needsLogin=false).
  if (needsLogin()) return <Navigate to="/login" replace />
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-100 via-slate-50 to-slate-200/60 text-slate-900">
      <header className="sticky top-0 z-20 border-b border-slate-200/70 bg-white/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-2.5">
          {/* 로고 마크 */}
          <span className="flex shrink-0 items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-600 to-violet-600 text-base text-white shadow-glow">
              🛡️
            </span>
            <span className="hidden flex-col leading-none md:flex">
              <span className="text-[15px] font-bold tracking-tight text-slate-900">CNAPP 관제</span>
              <span className="text-[10px] text-slate-400">멀티클라우드 보안 플랫폼</span>
            </span>
          </span>

          {/* 내비 — 활성 pill. no-scrollbar로 좁은 화면에서만 조용히 스크롤(바 숨김) */}
          <nav className="no-scrollbar ml-1 flex gap-0.5 overflow-x-auto text-[13px]">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  `whitespace-nowrap rounded-lg px-2.5 py-1.5 font-medium transition ${
                    isActive ? 'bg-brand-600 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex shrink-0 items-center gap-3">
            <RoleSwitcher />
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
                IS_MOCK ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${IS_MOCK ? 'bg-amber-500' : 'bg-emerald-500'}`} />
              {IS_MOCK ? '목업' : '실데이터'}
            </span>
            {!IS_MOCK && isAuthenticated() && <UserMenu />}
          </div>
        </div>
      </header>
      {/* key=pathname → 라우트 전환마다 진입 fade-up 재생(프리미엄 감) */}
      <main key={location.pathname} className="mx-auto max-w-7xl animate-fade-up px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
