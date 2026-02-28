"use client"

import { useEffect, useRef, useMemo, useCallback } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { useResearchStore } from "@/store/research"
import { useTranslations } from "next-intl"

const REMARKGFM_PLUGINS = [remarkGfm]

export function StreamingDraftViewer() {
  const t = useTranslations("workspace")
  const streamingText = useResearchStore((s) => s.streamingText)
  const isStreaming = useResearchStore((s) => s.isStreaming)
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollRafRef = useRef<number | null>(null)

  const scrollToBottom = useCallback(() => {
    if (scrollRafRef.current !== null) return
    scrollRafRef.current = requestAnimationFrame(() => {
      scrollRafRef.current = null
      bottomRef.current?.scrollIntoView({ behavior: "auto" })
    })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [streamingText, scrollToBottom])

  useEffect(() => {
    return () => {
      if (scrollRafRef.current !== null) cancelAnimationFrame(scrollRafRef.current)
    }
  }, [])

  const renderedMarkdown = useMemo(
    () => (
      <ReactMarkdown remarkPlugins={REMARKGFM_PLUGINS}>
        {streamingText}
      </ReactMarkdown>
    ),
    [streamingText]
  )

  if (!isStreaming && !streamingText) return null

  return (
    <article className="prose prose-zinc dark:prose-invert max-w-none">
      <div className="flex items-center gap-2 mb-4">
        <div className="flex gap-1">
          <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
          <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse [animation-delay:150ms]" />
          <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse [animation-delay:300ms]" />
        </div>
        <span className="text-sm text-zinc-500 dark:text-zinc-400">
          {t("streamingLabel")}
        </span>
      </div>
      <div className="text-zinc-700 dark:text-zinc-300 leading-relaxed">
        {renderedMarkdown}
        {isStreaming && (
          <span className="inline-block w-0.5 h-5 bg-zinc-600 dark:bg-zinc-300 animate-pulse ml-0.5 align-text-bottom" />
        )}
      </div>
      <div ref={bottomRef} />
    </article>
  )
}
