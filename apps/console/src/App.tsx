import { NavLink, Outlet } from 'react-router-dom'

const NAV = [
  { to: '/', label: '대시보드', end: true },
  { to: '/findings', label: 'Findings' },
  { to: '/attack-paths', label: 'Attack-path' },
  { to: '/remediation', label: '조치' },
  { to: '/compliance', label: '컴플라이언스' },
  { to: '/audit', label: '감사로그' },
]

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
          <span className="text-lg font-bold">CNAPP 관제</span>
          <nav className="flex gap-1 text-sm">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  `rounded px-3 py-1.5 ${
                    isActive ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <span className="ml-auto text-xs text-slate-400">
            {import.meta.env.VITE_USE_MOCK !== 'false' ? '● 목업 모드 (MSW)' : '● 실데이터'}
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
