import type { Metadata } from 'next'
import './globals.css'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import { LanguageProvider } from '@/context/LanguageContext'

export const metadata: Metadata = {
  title: 'XiaoYueDict — AI Pronunciation Assessment',
  description: 'AI-powered pronunciation scoring for English and Chinese. Get word-level feedback in 5 seconds.',
  keywords: ['pronunciation', 'AI', 'scoring', 'English', 'Chinese', 'Mandarin', 'HSK', 'IELTS'],
  openGraph: {
    title: 'XiaoYueDict — AI Pronunciation Assessment',
    description: 'AI-powered pronunciation scoring for English and Chinese.',
    type: 'website',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="vi">
      <head>
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0..1,0" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="theme-color" content="#334155" />
      </head>
      <body className="font-lexend text-primary bg-content-bg">
        <LanguageProvider>
          <div className="flex h-screen w-full bg-content-bg overflow-hidden font-lexend text-primary">
            <Sidebar />
            <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
              <Header />
              {/* Main Content Area */}
              {children}
            </div>
          </div>
        </LanguageProvider>
      </body>
    </html>
  )
}
