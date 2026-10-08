/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#05050A',
          900: '#0A0A12',
          850: '#0F0F19',
          800: '#151521',
          700: '#1E1E2C',
        },
        accent: {
          DEFAULT: '#B9A6FF',
          strong: '#8B6CFF',
          soft: 'rgba(185, 166, 255, 0.12)',
        },
        gold: '#F2D29B',
        aqua: '#7FE7FF',
        rose: { glow: '#FF8FB1' },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        display: ['"Instrument Serif"', 'ui-serif', 'Georgia', 'serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 0 0 rgba(255,255,255,0.05) inset, 0 30px 60px -30px rgba(0,0,0,0.9)',
        glow: '0 0 0 1px rgba(185,166,255,0.25), 0 10px 40px -10px rgba(139,108,255,0.55)',
        'glow-lg': '0 0 80px -10px rgba(139,108,255,0.45)',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-400px 0' },
          '100%': { backgroundPosition: '400px 0' },
        },
        // Opacity + transform only: GPU-cheap on every device.
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-8px)' },
        },
        'progress-sheen': {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(200%)' },
        },
        drift: {
          '0%, 100%': { transform: 'translate3d(0, 0, 0) scale(1)' },
          '33%': { transform: 'translate3d(6%, -4%, 0) scale(1.08)' },
          '66%': { transform: 'translate3d(-5%, 5%, 0) scale(0.95)' },
        },
        'gradient-x': {
          '0%, 100%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
        },
        'spin-border': {
          to: { '--angle': '360deg' },
        },
        orbit: {
          to: { transform: 'rotate(360deg)' },
        },
        'pulse-ring': {
          '0%': { transform: 'scale(0.85)', opacity: '0.6' },
          '100%': { transform: 'scale(1.6)', opacity: '0' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.6s linear infinite',
        'fade-up': 'fade-up 0.7s cubic-bezier(0.22, 1, 0.36, 1) both',
        float: 'float 7s ease-in-out infinite',
        'progress-sheen': 'progress-sheen 1.8s ease-in-out infinite',
        drift: 'drift 22s ease-in-out infinite',
        'drift-slow': 'drift 34s ease-in-out infinite reverse',
        'gradient-x': 'gradient-x 8s ease infinite',
        'spin-border': 'spin-border 6s linear infinite',
        orbit: 'orbit 14s linear infinite',
        'orbit-fast': 'orbit 6s linear infinite',
        'pulse-ring': 'pulse-ring 2.4s cubic-bezier(0.22, 1, 0.36, 1) infinite',
      },
    },
  },
  plugins: [],
}
