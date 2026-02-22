"use client"

import { useState } from "react"
import type { Paper } from "@/types"

interface CitationTooltipProps {
  citationId: string
  papers: Paper[]
  children: React.ReactNode
}

export function CitationTooltip({ citationId, papers, children }: CitationTooltipProps) {
  const [isVisible, setIsVisible] = useState(false)
  const paper = papers.find((p) => p.paper_id === citationId)

  if (!paper) {
    return <span className="text-blue-500">{children}</span>
  }

  return (
    <span
      className="relative inline-block"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      <span className="text-blue-500 cursor-help underline decoration-dotted">
        {children}
      </span>
      {isVisible && (
        <span className="absolute left-0 top-full z-50 mt-1 w-80 rounded-md border border-zinc-200 bg-white p-3 shadow-lg dark:border-zinc-700 dark:bg-zinc-800 block">
          <span className="block font-medium text-sm text-zinc-900 dark:text-zinc-100 line-clamp-2">
            {paper.title}
          </span>
          <span className="block mt-1 text-xs text-zinc-500 dark:text-zinc-400 line-clamp-1">
            {paper.authors.slice(0, 3).join(", ")}
            {paper.authors.length > 3 && " et al."}
            {paper.year && ` (${paper.year})`}
          </span>
          {paper.url && (
            <a
              href={paper.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 block text-xs text-blue-500 hover:underline"
            >
              View paper →
            </a>
          )}
          {paper.pdf_url && (
            <a
              href={paper.pdf_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 block text-xs text-green-600 hover:underline dark:text-green-400"
            >
              📄 Download PDF →
            </a>
          )}
        </span>
      )}
    </span>
  )
}
