"use client"

import { useEffect, useRef } from "react"
import { useResearchStore } from "@/store/research"
import { useTranslations, useLocale } from 'next-intl'

export function LogStream() {
  const logs = useResearchStore((s) => s.logs)
  const scrollRef = useRef<HTMLDivElement>(null)
  const t = useTranslations('log')
  const locale = useLocale()

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs])

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString(locale === 'zh' ? 'zh-CN' : 'en-US', {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    })
  }

  return (
    <div
      ref={scrollRef}
      className="flex-1 overflow-y-auto bg-zinc-950 p-3 font-mono text-xs"
    >
      {logs.length === 0 ? (
        <p className="text-zinc-500">{t('waiting')}</p>
      ) : (
        logs.map((log, i) => (
          <div key={i} className="mb-1">
            <span className="text-zinc-500">[{formatTime(log.timestamp)}]</span>{" "}
            <span className="text-emerald-400">{log.node}</span>{" "}
            <span className="text-zinc-300">{log.message}</span>
          </div>
        ))
      )}
    </div>
  )
}
