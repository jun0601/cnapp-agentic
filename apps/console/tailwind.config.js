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
        // 브랜드/AI 액센트
        brand: {
          DEFAULT: '#4f46e5',
          50: '#eef2ff',
          100: '#e0e7ff',
          600: '#4f46e5',
          700: '#4338ca',
        },
      },
      boxShadow: {
        card: '0 1px 2px rgba(15,23,42,0.04), 0 2px 8px rgba(15,23,42,0.05)',
        cardhover: '0 6px 20px rgba(15,23,42,0.10), 0 2px 6px rgba(15,23,42,0.05)',
        glow: '0 0 0 1px rgba(79,70,229,0.15), 0 8px 24px rgba(79,70,229,0.18)',
      },
      keyframes: {
        'fade-up': { '0%': { opacity: '0', transform: 'translateY(6px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
      },
      animation: { 'fade-up': 'fade-up 0.35s ease-out both' },
    },
  },
  plugins: [],
}
