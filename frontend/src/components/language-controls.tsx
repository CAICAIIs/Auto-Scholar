"use client"

import { useTransition } from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { useResearchStore, persistStoreState } from '@/store/research'

export function LanguageControls() {
  const locale = useLocale()
  const t = useTranslations('language')
  const outputLanguage = useResearchStore((s) => s.outputLanguage)
  const setOutputLanguage = useResearchStore((s) => s.setOutputLanguage)
  const [isPending, startTransition] = useTransition()

  const switchLocale = () => {
    const newLocale = locale === 'en' ? 'zh' : 'en'
    startTransition(() => {
      persistStoreState()
      document.cookie = `locale=${newLocale};path=/;max-age=31536000`
      window.location.reload()
    })
  }

  const toggleOutputLanguage = () => {
    setOutputLanguage(outputLanguage === 'en' ? 'zh' : 'en')
  }

  return (
    <div className="flex items-center gap-1.5">
      <button
        onClick={switchLocale}
        disabled={isPending}
        className="flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors disabled:opacity-50"
        title={t('uiLanguage')}
      >
        <span>{t('uiLabel')}</span>
        <span className="inline-flex items-center rounded bg-zinc-800 border border-zinc-700">
          <span
            className={`px-1 py-px rounded-sm transition-colors ${
              locale === 'zh'
                ? 'bg-zinc-600 text-zinc-100'
                : 'text-zinc-500'
            }`}
          >
            中
          </span>
          <span
            className={`px-1 py-px rounded-sm transition-colors ${
              locale === 'en'
                ? 'bg-zinc-600 text-zinc-100'
                : 'text-zinc-500'
            }`}
          >
            EN
          </span>
        </span>
      </button>

      <div className="w-px h-3 bg-zinc-700" />

      <button
        onClick={toggleOutputLanguage}
        className="flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
        title={t('outputLanguage')}
      >
        <span>{t('outputLabel')}</span>
        <span className="inline-flex items-center rounded bg-zinc-800 border border-zinc-700">
          <span
            className={`px-1 py-px rounded-sm transition-colors ${
              outputLanguage === 'zh'
                ? 'bg-zinc-600 text-zinc-100'
                : 'text-zinc-500'
            }`}
          >
            中
          </span>
          <span
            className={`px-1 py-px rounded-sm transition-colors ${
              outputLanguage === 'en'
                ? 'bg-zinc-600 text-zinc-100'
                : 'text-zinc-500'
            }`}
          >
            EN
          </span>
        </span>
      </button>
    </div>
  )
}
