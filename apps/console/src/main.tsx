import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { router } from './router'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
})

// 목업 우선(§15.5): VITE_USE_MOCK=true면 MSW를 켜고 나서 앱 렌더.
async function bootstrap() {
  if (import.meta.env.VITE_USE_MOCK !== 'false') {
    const { startMockWorker } = await import('./mocks/browser')
    await startMockWorker()
  }

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </React.StrictMode>,
  )
}

bootstrap()
