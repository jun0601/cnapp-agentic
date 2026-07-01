import { NavLink, Outlet } from 'react-router-dom'
import { IS_MOCK, useRole, setRole, type Role } from '@/lib/auth'

const NAV = [
  { to: '/', label: '대시보드', end: true },
  { to: '/findings', label: 'Findings' },
  { to: '/attack-paths', label: 'Attack-path' },
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
        className="rounded border border-slate-300 bg-white px-2 py-1 text-slate-700"
        title="개발용 역할 전환 (실데이터에선 Cognito custom:groups로 판정)"
      >
        <option value="viewer">viewer</option>
        <option value="approver">approver</option>
      </select>
    </label>
  )
}

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-2.5">
          <span className="flex items-center gap-2 font-bold">
            <img src="/favicon.svg" alt="" className="h-6 w-6" />
            <span className="text-slate-900">CNAPP 관제</span>
          </span>
          <nav className="ml-2 flex gap-1 text-sm">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  `rounded-md px-3 py-1.5 transition ${
                    isActive ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <RoleSwitcher />
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                IS_MOCK ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'
              }`}
            >
              {IS_MOCK ? '목업 모드 (MSW)' : '실데이터'}
            </span>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
