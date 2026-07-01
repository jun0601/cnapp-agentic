/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // severity_id 내부 컨벤션(1=Critical~5=Info) 색상 토큰
        sev: {
          1: '#dc2626', // Critical
          2: '#ea580c', // High
          3: '#d97706', // Medium
          4: '#ca8a04', // Low
          5: '#6b7280', // Info
        },
        // 클라우드 레인(2.2 크로스클라우드 시각화)
        aws: '#ff9900',
        azure: '#0078d4',
      },
    },
  },
  plugins: [],
}
