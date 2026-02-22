"use client"

import { useEffect, useRef } from "react"
import { useResearchStore } from "@/store/research"
import { cn } from "@/lib/utils"

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

export function ChatThread() {
  const messages = useResearchStore((s) => s.messages)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  if (messages.length === 0) {
    return null
  }

  return (
    <div
      ref={scrollRef}
      className="flex-1 overflow-y-auto px-3 py-2 space-y-3 min-h-0"
    >
      {messages.map((msg, idx) => (
        <div
          key={idx}
          className={cn(
            "flex flex-col gap-1",
            msg.role === "user" ? "items-end" : "items-start"
          )}
        >
          <div
            className={cn(
              "max-w-[85%] rounded-lg px-3 py-2 text-sm",
              msg.role === "user"
                ? "bg-blue-600 text-white"
                : msg.role === "assistant"
                ? "bg-zinc-700 text-zinc-100"
                : "bg-zinc-800 text-zinc-400 text-xs"
            )}
          >
            {msg.content}
          </div>
          <span className="text-[10px] text-zinc-500 px-1">
            {formatTime(msg.timestamp)}
          </span>
        </div>
      ))}
    </div>
  )
}
