import { createBrowserRouter } from 'react-router-dom'
import App from './App'
import Dashboard from './pages/Dashboard'
import Findings from './pages/Findings'
import FindingDetail from './pages/FindingDetail'
import AttackPath from './pages/AttackPath'
import Remediation from './pages/Remediation'
import Compliance from './pages/Compliance'
import Audit from './pages/Audit'
import Login from './pages/Login'

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
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
    ],
  },
])
