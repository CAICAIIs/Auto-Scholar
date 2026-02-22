"use client"

import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { useResearchStore } from '@/store/research'

export function OutputLanguageSelector() {
  const t = useTranslations('console')
  const outputLanguage = useResearchStore((s) => s.outputLanguage)
  const setOutputLanguage = useResearchStore((s) => s.setOutputLanguage)

  const toggleLanguage = () => {
    const newLanguage = outputLanguage === 'en' ? 'zh' : 'en'
    setOutputLanguage(newLanguage)
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={toggleLanguage}
      className="gap-1.5 text-zinc-400 hover:text-zinc-100"
      title={outputLanguage === 'en' ? t('outputLanguageEnglish') : t('outputLanguageChinese')}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width={20}
        height={20}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        suppressHydrationWarning
      >
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
      {outputLanguage === 'en' ? 'EN' : '中'}
    </Button>
  )
}
