"use client"

import { useTranslations } from 'next-intl'
import { QueryInput } from "./query-input"
import { LogStream } from "./log-stream"
import { StatusIndicator } from "./status-indicator"
import { HistoryPanel } from "./history-panel"
import { ChatThread } from "./chat-thread"
import { LanguageSwitcher } from "@/components/language-switcher"
import { OutputLanguageSelector } from "@/components/output-language-selector"
import { useResearchStore } from "@/store/research"

interface AgentConsoleProps {
  onStartResearch: (query: string) => void
  onContinueResearch?: (message: string) => void
  onNewTopic?: () => void
}

export function AgentConsole({ onStartResearch, onContinueResearch, onNewTopic }: AgentConsoleProps) {
  const t = useTranslations('console')
  const messages = useResearchStore((s) => s.messages)
  const hasMessages = messages.length > 0

  return (
    <div className="flex flex-col h-full bg-zinc-900 border-r border-zinc-800">
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800">
        <h2 className="text-sm font-semibold text-zinc-100">{t('title')}</h2>
        <div className="flex items-center gap-1">
          <OutputLanguageSelector />
          <LanguageSwitcher />
        </div>
      </div>
      <QueryInput onSubmit={onStartResearch} onContinue={onContinueResearch} onNewTopic={onNewTopic} />
      {hasMessages ? <ChatThread /> : <LogStream />}
      <StatusIndicator />
      <HistoryPanel />
    </div>
  )
}
