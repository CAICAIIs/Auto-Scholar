"use client"

import { useTranslations } from 'next-intl'
import { QueryInput } from "./query-input"
import { LogStream } from "./log-stream"
import { StatusIndicator } from "./status-indicator"
import { HistoryPanel } from "./history-panel"
import { ChatThread } from "./chat-thread"
import { LanguageControls } from "@/components/language-controls"
import { ModelSelector } from "@/components/model-selector"
import { useResearchStore } from "@/store/research"

interface AgentConsoleProps {
  onStartResearch: (query: string) => void
  onContinueResearch?: (message: string) => void
  onNewTopic?: () => void
  collapsed?: boolean
  onToggleCollapse?: () => void
}

export function AgentConsole({ onStartResearch, onContinueResearch, onNewTopic, collapsed, onToggleCollapse }: AgentConsoleProps) {
  const t = useTranslations('console')
  const messages = useResearchStore((s) => s.messages)
  const hasMessages = messages.length > 0

  if (collapsed) {
    return (
      <div className="flex flex-col items-center h-full bg-zinc-900 border-r border-zinc-800 py-2">
        <button
          onClick={onToggleCollapse}
          className="p-1.5 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded transition-colors"
          title={t('expand')}
        >
          <svg xmlns="http://www.w3.org/2000/svg" width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" suppressHydrationWarning>
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-zinc-900 border-r border-zinc-800">
      <div className="border-b border-zinc-800">
        <div className="flex items-center justify-between px-3 py-2">
          <h2 className="text-sm font-semibold text-zinc-100">{t('title')}</h2>
          <button
            onClick={onToggleCollapse}
            className="p-1 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded transition-colors"
            title={t('collapse')}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" suppressHydrationWarning>
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
        </div>
        <div className="flex items-center gap-2 px-3 pb-2">
          <ModelSelector />
          <div className="w-px h-3 bg-zinc-700" />
          <LanguageControls />
        </div>
      </div>
      <QueryInput onSubmit={onStartResearch} onContinue={onContinueResearch} onNewTopic={onNewTopic} />
      {hasMessages ? <ChatThread /> : <LogStream />}
      <StatusIndicator />
      <HistoryPanel />
    </div>
  )
}
