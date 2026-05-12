import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Lexend', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        lexend: ['Lexend', 'sans-serif'],
      },
      colors: {
        primary: 'var(--color-primary)',
        secondary: 'var(--color-secondary)',
        tertiary: 'var(--color-tertiary)',
        sage: 'var(--color-sage)',
        orange: 'var(--color-orange)',
        surface: 'var(--color-surface)',
        outline: 'var(--color-outline)',
        'hover-bg': 'var(--color-hover-bg)',
        'content-bg': 'var(--color-content-bg)',
      }
    },
  },
  plugins: [],
}
export default config
