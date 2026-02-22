"use client"

import { useTranslations } from 'next-intl'
import { useResearchStore, type WorkflowStatus } from "@/store/research"

const statusColors: Record<WorkflowStatus, string> = {
  idle: "bg-zinc-500",
  searching: "bg-blue-500 animate-pulse",
  waiting_approval: "bg-amber-500",
  processing: "bg-blue-500 animate-pulse",
  drafting: "bg-purple-500 animate-pulse",
  continuing: "bg-purple-500 animate-pulse",
  completed: "bg-emerald-500",
  error: "bg-red-500",
}

export function StatusIndicator() {
  const t = useTranslations('status')
  const status = useResearchStore((s) => s.status)
  const error = useResearchStore((s) => s.error)

  return (
    <div className="flex items-center gap-2 px-3 py-2 border-t border-zinc-800 text-sm">
      <div className={`w-2 h-2 rounded-full ${statusColors[status]}`} />
      <span className="text-zinc-400">{t(status)}</span>
      {error && <span className="text-red-400 text-xs truncate">({error})</span>}
    </div>
  )
}
