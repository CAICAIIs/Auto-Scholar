"use client"

import { cn } from "@/lib/utils"
import type { Paper } from "@/types"
import type { PaperProcessingStatus } from "@/store/research"

interface PaperCardProps {
  paper: Paper
  status: PaperProcessingStatus
  message?: string
  index: number
}

const sourceLabels: Record<string, string> = {
  semantic_scholar: "S2",
  arxiv: "arXiv",
  pubmed: "PubMed",
}

const statusStyles: Record<PaperProcessingStatus, string> = {
  pending: "border-zinc-700 bg-zinc-800/50",
  processing: "border-blue-500 bg-blue-500/10 shadow-[0_0_15px_rgba(59,130,246,0.3)]",
  completed: "border-emerald-500/50 bg-emerald-500/5",
  failed: "border-red-500/50 bg-red-500/5",
}

const statusIcons: Record<PaperProcessingStatus, string> = {
  pending: "○",
  processing: "◉",
  completed: "✓",
  failed: "✗",
}

export function PaperCard({ paper, status, message, index }: PaperCardProps) {
  const authors = paper.authors.slice(0, 2).join(", ")
  const hasMoreAuthors = paper.authors.length > 2

  return (
    <div
      className={cn(
        "relative rounded-lg border p-3 transition-all duration-500",
        "animate-in fade-in slide-in-from-bottom-2",
        statusStyles[status]
      )}
      style={{ animationDelay: `${index * 100}ms`, animationFillMode: "backwards" }}
    >
      <div className="flex items-start gap-3">
        <div className={cn(
          "flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-mono",
          status === "pending" && "bg-zinc-700 text-zinc-400",
          status === "processing" && "bg-blue-500 text-white animate-pulse",
          status === "completed" && "bg-emerald-500 text-white",
          status === "failed" && "bg-red-500 text-white"
        )}>
          {statusIcons[status]}
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={cn(
              "text-[10px] px-1.5 py-0.5 rounded font-medium",
              "bg-zinc-700 text-zinc-300"
            )}>
              {sourceLabels[paper.source || "semantic_scholar"]}
            </span>
            {paper.year && (
              <span className="text-[10px] text-zinc-500">{paper.year}</span>
            )}
          </div>
          
          <h4 className={cn(
            "text-sm font-medium leading-tight mb-1 line-clamp-2",
            status === "processing" ? "text-blue-100" : "text-zinc-200"
          )}>
            {paper.title}
          </h4>
          
          <p className="text-xs text-zinc-500 truncate">
            {authors}{hasMoreAuthors && " et al."}
          </p>
          
          {status === "processing" && message && (
            <p className="text-xs text-blue-400 mt-2 animate-pulse">
              {message}
            </p>
          )}
          
          {status === "completed" && paper.core_contribution && (
            <p className="text-xs text-emerald-400/80 mt-2 line-clamp-2">
              {paper.core_contribution}
            </p>
          )}
        </div>
      </div>
      
      {status === "processing" && (
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-zinc-700 overflow-hidden rounded-b-lg">
          <div className="h-full bg-blue-500 animate-progress-indeterminate" />
        </div>
      )}
    </div>
  )
}
