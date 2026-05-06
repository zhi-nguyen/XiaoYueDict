import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'XiaoYue Dict - English Assessment',
  description: 'AI-powered English pronunciation assessment',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
