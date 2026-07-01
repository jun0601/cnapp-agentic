// MSW 브라우저 워커. main.tsx가 MOCK=true일 때만 start.
import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

export const worker = setupWorker(...handlers)

export async function startMockWorker() {
  await worker.start({
    onUnhandledRequest: 'bypass', // 정적 자산 등은 통과
  })
  // eslint-disable-next-line no-console
  console.info('[MSW] 목업 모드 — contracts/mock-*.json 서빙 중')
}
