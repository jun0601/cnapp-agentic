import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

// 목업 우선: MSW 핸들러가 contracts/mock-*.json을 직접 import 한다.
// contracts/는 apps/console 밖(레포 루트)이라 vite fs.allow + alias로 접근 허용.
const repoRoot = fileURLToPath(new URL('../../', import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@contracts': fileURLToPath(new URL('../../contracts', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    fs: {
      // 레포 루트를 허용해야 ../../contracts/*.json import 가능
      allow: [repoRoot],
    },
  },
})
