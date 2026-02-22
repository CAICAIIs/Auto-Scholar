"use client"

import { useEffect, useRef } from "react"
import { useResearchStore } from "@/store/research"
import { PaperCard } from "./paper-card"
import { StageIndicator } from "./stage-indicator"
import { useTranslations } from "next-intl"

export function ProcessingVisualizer() {
  const t = useTranslations("processing")
  const scrollRef = useRef<HTMLDivElement>(null)
  
  const candidatePapers = useResearchStore((s) => s.candidatePapers)
  const selectedPaperIds = useResearchStore((s) => s.selectedPaperIds)
  const processingStage = useResearchStore((s) => s.processingStage)
  const paperProcessingStates = useResearchStore((s) => s.paperProcessingStates)
  const processingStartTime = useResearchStore((s) => s.processingStartTime)

  const selectedPapers = candidatePapers.filter(p => selectedPaperIds.has(p.paper_id))
  
  const completedCount = Array.from(paperProcessingStates.values())
    .filter(s => s.status === "completed").length

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth"
      })
    }
  }, [paperProcessingStates])

  const elapsedSeconds = processingStartTime 
    ? Math.floor((Date.now() - processingStartTime) / 1000)
    : 0

  return (
    <div className="flex flex-col h-full bg-zinc-900 rounded-lg border border-zinc-800 overflow-hidden">
      <div className="flex-shrink-0 border-b border-zinc-800 px-4 py-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-zinc-100">
            {t("title")}
          </h3>
          <div className="flex items-center gap-3 text-xs text-zinc-500">
            <span>{selectedPapers.length} {t("papers")}</span>
            {processingStartTime && (
              <span className="font-mono">{formatTime(elapsedSeconds)}</span>
            )}
          </div>
        </div>
        
        <StageIndicator 
          currentStage={processingStage}
          paperCount={selectedPapers.length}
          completedCount={completedCount}
        />
      </div>

      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-3"
      >
        {selectedPapers.map((paper, index) => {
          const state = paperProcessingStates.get(paper.paper_id)
          return (
            <PaperCard
              key={paper.paper_id}
              paper={paper}
              status={state?.status || "pending"}
              message={state?.message}
              index={index}
            />
          )
        })}
      </div>

      {processingStage === "drafting" && (
        <div className="flex-shrink-0 border-t border-zinc-800 px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-purple-400">
            <span className="animate-pulse">✍️</span>
            <span>{t("draftingMessage")}</span>
          </div>
        </div>
      )}

      {processingStage === "qa" && (
        <div className="flex-shrink-0 border-t border-zinc-800 px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-amber-400">
            <span className="animate-pulse">✅</span>
            <span>{t("qaMessage")}</span>
          </div>
        </div>
      )}
    </div>
  )
}

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}:${secs.toString().padStart(2, "0")}`
}
