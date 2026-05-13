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
      <head>
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0..1,0" />
      </head>
      <body className="font-lexend text-primary bg-content-bg">{children}</body>
    </html>
  )
}
