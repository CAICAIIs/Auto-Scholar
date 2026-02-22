"use client"

import { useState, useSyncExternalStore } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { useTranslations } from 'next-intl'
import { useResearchStore } from "@/store/research"
import type { PaperSource } from "@/types"

interface QueryInputProps {
  onSubmit: (query: string) => void
  onContinue?: (message: string) => void
  onNewTopic?: () => void
}

const EXAMPLE_KEYS = ['example1', 'example2', 'example3', 'example4', 'example5'] as const

const SOURCES: { id: PaperSource; labelKey: string }[] = [
  { id: "semantic_scholar", labelKey: "sourceSemanticScholar" },
  { id: "arxiv", labelKey: "sourceArxiv" },
  { id: "pubmed", labelKey: "sourcePubmed" },
]

const emptySubscribe = () => () => {}
const getClientSnapshot = () => true
const getServerSnapshot = () => false

export function QueryInput({ onSubmit, onContinue, onNewTopic }: QueryInputProps) {
  const [query, setQuery] = useState("")
  const t = useTranslations('query')
  const status = useResearchStore((s) => s.status)
  const draft = useResearchStore((s) => s.draft)
  const searchSources = useResearchStore((s) => s.searchSources)
  const toggleSearchSource = useResearchStore((s) => s.toggleSearchSource)
  const isLoading = status !== "idle" && status !== "completed" && status !== "error"
  const canContinue = status === "completed" && draft !== null && onContinue !== undefined
  
  const hasMounted = useSyncExternalStore(emptySubscribe, getClientSnapshot, getServerSnapshot)

  const getCheckedState = (sourceId: PaperSource) => {
    if (!hasMounted) {
      return sourceId === "semantic_scholar"
    }
    return searchSources.includes(sourceId)
  }

  const getDisabledState = (sourceId: PaperSource) => {
    if (!hasMounted) {
      return false
    }
    return isLoading || (searchSources.length === 1 && searchSources.includes(sourceId))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim() || isLoading) return
    
    if (canContinue) {
      onContinue(query.trim())
    } else {
      onSubmit(query.trim())
    }
    setQuery("")
  }

  const handleExampleClick = (exampleKey: typeof EXAMPLE_KEYS[number]) => {
    if (isLoading) return
    const exampleText = t(exampleKey)
    setQuery(exampleText)
  }

  const getButtonText = () => {
    if (isLoading) return t('running')
    if (canContinue) return t('continue') || 'Continue'
    return t('start')
  }

  const getPlaceholder = () => {
    if (canContinue) return t('continuePlaceholder') || 'Ask a follow-up question...'
    return t('placeholder')
  }

  return (
    <div className="border-b border-zinc-800">
      <form onSubmit={handleSubmit} className="flex gap-2 p-3">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={getPlaceholder()}
          disabled={isLoading}
          className="flex-1 bg-zinc-900 border-zinc-700 text-zinc-100 placeholder:text-zinc-500"
        />
        <Button type="submit" disabled={isLoading || !query.trim()}>
          {getButtonText()}
        </Button>
      </form>
      
      {canContinue && onNewTopic && (
        <div className="px-3 pb-3">
          <button
            type="button"
            onClick={onNewTopic}
            className="text-xs text-zinc-500 hover:text-zinc-300 underline"
          >
            {t('newTopic') || 'Start new topic'}
          </button>
        </div>
      )}

      {!canContinue && (
        <>
          <div className="px-3 pb-2">
            <span className="text-xs text-zinc-500">{t('sources')}</span>
            <div className="flex flex-wrap gap-3 mt-1.5">
              {SOURCES.map((source) => (
                <label
                  key={source.id}
                  className="flex items-center gap-1.5 text-xs text-zinc-400 cursor-pointer hover:text-zinc-200"
                >
                  <Checkbox
                    checked={getCheckedState(source.id)}
                    onCheckedChange={() => hasMounted && toggleSearchSource(source.id)}
                    disabled={getDisabledState(source.id)}
                    className="h-3.5 w-3.5 border-zinc-600 data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600"
                  />
                  {t(source.labelKey)}
                </label>
              ))}
            </div>
          </div>

          <div className="px-3 pb-3">
            <span className="text-xs text-zinc-500 mr-2">{t('examples')}</span>
            <div className="flex flex-wrap gap-1.5 mt-1.5">
              {EXAMPLE_KEYS.map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => handleExampleClick(key)}
                  disabled={isLoading}
                  className="text-xs px-2 py-1 rounded-md bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {t(key)}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
