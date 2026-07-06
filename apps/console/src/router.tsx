import { createBrowserRouter } from 'react-router-dom'
import App from './App'
import Dashboard from './pages/Dashboard'
import Findings from './pages/Findings'
import FindingDetail from './pages/FindingDetail'
import AttackPath from './pages/AttackPath'
import Remediation from './pages/Remediation'
import Compliance from './pages/Compliance'
import Audit from './pages/Audit'
import Chat from './pages/Chat'
import Login from './pages/Login'
import Callback from './pages/Callback'

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  { path: '/callback', element: <Callback /> }, // OIDC 리다이렉트(옵션 B)
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'findings', element: <Findings /> },
      { path: 'findings/:id', element: <FindingDetail /> },
      { path: 'attack-paths', element: <AttackPath /> },
      { path: 'attack-paths/:id', element: <AttackPath /> },
      { path: 'remediation', element: <Remediation /> },
      { path: 'compliance', element: <Compliance /> },
      { path: 'audit', element: <Audit /> },
      { path: 'chat', element: <Chat /> },
    ],
  },
])
