"use client"

import { useTransition } from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'

export function LanguageSwitcher() {
  const locale = useLocale()
  const t = useTranslations('language')
  const [isPending, startTransition] = useTransition()

  const switchLocale = () => {
    const newLocale = locale === 'en' ? 'zh' : 'en'
    startTransition(() => {
      document.cookie = `locale=${newLocale};path=/;max-age=31536000`
      window.location.reload()
    })
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={switchLocale}
      disabled={isPending}
      className="gap-1.5 text-zinc-400 hover:text-zinc-100"
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
        <path d="M5 8h14M2 8v2M22 8v2M3 12h1M4 12h1M20 12h1M12 22a1 1 0 1 1-1 1h-6a1 1 0 1 1-1 1v-6a1 1 0 1 1 1 1z" />
        <path d="M4 6h16M4 12h16M4 18h16" />
      </svg>
      {t('switch')}
    </Button>
  )
}
