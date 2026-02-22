"use client"

import { useEffect, useState } from "react"
import { useTranslations } from 'next-intl'
import { Button } from "@/components/ui/button"
import { listSessions, getSession } from "@/lib/api/client"
import { useResearchStore } from "@/store/research"
import type { SessionSummary } from "@/types"

interface HistoryPanelProps {
  onSessionLoaded?: () => void
}

export function HistoryPanel({ onSessionLoaded }: HistoryPanelProps) {
  const t = useTranslations('console')
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingSession, setLoadingSession] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)

  const setThreadId = useResearchStore((s) => s.setThreadId)
  const setDraft = useResearchStore((s) => s.setDraft)
  const setApprovedPapers = useResearchStore((s) => s.setApprovedPapers)
  const setStatus = useResearchStore((s) => s.setStatus)
  const status = useResearchStore((s) => s.status)

  const fetchSessions = async () => {
    setLoading(true)
    try {
      const data = await listSessions(20)
      setSessions(data.filter(s => s.has_draft))
    } catch (err) {
      console.error("Failed to fetch sessions:", err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (expanded && sessions.length === 0) {
      fetchSessions()
    }
  }, [expanded])

  const handleLoadSession = async (threadId: string) => {
    setLoadingSession(threadId)
    try {
      const detail = await getSession(threadId)
      setThreadId(detail.thread_id)
      setApprovedPapers(detail.approved_papers)
      setDraft(detail.final_draft)
      setStatus("completed")
      onSessionLoaded?.()
    } catch (err) {
      console.error("Failed to load session:", err)
    } finally {
      setLoadingSession(null)
    }
  }

  const isLoading = status !== "idle" && status !== "completed" && status !== "error"

  return (
    <div className="border-t border-zinc-800">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2 flex items-center justify-between text-sm text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50 transition-colors"
      >
        <span>{t('history')}</span>
        <svg
          className={`w-4 h-4 transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          suppressHydrationWarning
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      
      {expanded && (
        <div className="max-h-48 overflow-y-auto">
          {loading ? (
            <div className="px-3 py-4 text-center text-xs text-zinc-500">...</div>
          ) : sessions.length === 0 ? (
            <div className="px-3 py-4 text-center text-xs text-zinc-500">
              {t('historyEmpty')}
            </div>
          ) : (
            <div className="divide-y divide-zinc-800">
              {sessions.map((session) => (
                <div
                  key={session.thread_id}
                  className="px-3 py-2 hover:bg-zinc-800/50"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-zinc-300 truncate" title={session.user_query}>
                        {session.user_query}
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                          session.status === 'completed' 
                            ? 'bg-green-900/50 text-green-400'
                            : session.status === 'in_progress'
                            ? 'bg-yellow-900/50 text-yellow-400'
                            : 'bg-zinc-700 text-zinc-400'
                        }`}>
                          {t(`historyStatus.${session.status}`)}
                        </span>
                        <span className="text-[10px] text-zinc-500">
                          {t('historyPapers', { count: session.paper_count })}
                        </span>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={() => handleLoadSession(session.thread_id)}
                      disabled={isLoading || loadingSession === session.thread_id}
                      className="text-xs"
                    >
                      {loadingSession === session.thread_id ? "..." : t('historyLoad')}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
