"use client"

import { useEffect, useRef, useState } from "react"
import { useResearchStore } from "@/store/research"
import { PaperCard } from "./paper-card"
import { StageIndicator } from "./stage-indicator"
import { useTranslations } from "next-intl"
import { PenSquare, CheckCircle2 } from "lucide-react"

export function ProcessingVisualizer() {
  const t = useTranslations("processing")
  const scrollRef = useRef<HTMLDivElement>(null)
  const [isUserNearBottom, setIsUserNearBottom] = useState(true)
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0)

  const candidatePapers = useResearchStore((s) => s.candidatePapers)
  const selectedPaperIds = useResearchStore((s) => s.selectedPaperIds)
  const processingStage = useResearchStore((s) => s.processingStage)
  const paperProcessingStates = useResearchStore((s) => s.paperProcessingStates)
  const processingStartTime = useResearchStore((s) => s.processingStartTime)

  useEffect(() => {
    if (!processingStartTime) {
      return
    }

    const updateElapsed = () => {
      setElapsedSeconds(Math.floor((Date.now() - processingStartTime) / 1000))
    }

    updateElapsed()
    const interval = setInterval(updateElapsed, 1000)

    return () => {
      clearInterval(interval)
    }
  }, [processingStartTime])

  const selectedPapers = candidatePapers.filter(p => selectedPaperIds.has(p.paper_id))

  const completedCount = Array.from(paperProcessingStates.values())
    .filter(s => s.status === "completed").length

  const checkUserScrollPosition = () => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight
    setIsUserNearBottom(distanceFromBottom < 100)
  }

  useEffect(() => {
    const scrollElement = scrollRef.current
    if (!scrollElement) return

    scrollElement.addEventListener("scroll", checkUserScrollPosition)
    return () => {
      scrollElement.removeEventListener("scroll", checkUserScrollPosition)
    }
  }, [])

  useEffect(() => {
    if (scrollRef.current && isUserNearBottom) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth"
      })
    }
  }, [paperProcessingStates, isUserNearBottom])

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
            <span className="animate-pulse"><PenSquare className="h-4 w-4 inline-flex" /></span>
            <span>{t("draftingMessage")}</span>
          </div>
        </div>
      )}

      {processingStage === "qa" && (
        <div className="flex-shrink-0 border-t border-zinc-800 px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-amber-400">
            <span className="animate-pulse"><CheckCircle2 className="h-4 w-4 inline-flex" /></span>
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
