"use client"

import { cn } from "@/lib/utils"
import type { ProcessingStage } from "@/store/research"
import { useTranslations } from "next-intl"
import { BookOpen, PenLine, CheckCircle2 } from "lucide-react"

interface StageIndicatorProps {
  currentStage: ProcessingStage | null
  paperCount: number
  completedCount: number
}

const stages: { id: ProcessingStage; icon: React.ReactNode }[] = [
  { id: "extracting", icon: <BookOpen className="h-4 w-4" /> },
  { id: "drafting", icon: <PenLine className="h-4 w-4" /> },
  { id: "qa", icon: <CheckCircle2 className="h-4 w-4" /> },
]

export function StageIndicator({ currentStage, paperCount, completedCount }: StageIndicatorProps) {
  const t = useTranslations("processing")
  
  const currentIndex = currentStage ? stages.findIndex(s => s.id === currentStage) : -1

  return (
    <div className="flex items-center justify-center gap-2 py-4">
      {stages.map((stage, index) => {
        const isActive = stage.id === currentStage
        const isCompleted = currentIndex > index
        const isPending = currentIndex < index

        return (
          <div key={stage.id} className="flex items-center">
            <div className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-full text-sm transition-all duration-300",
              isActive && "bg-blue-500/20 text-blue-300 scale-105",
              isCompleted && "bg-emerald-500/20 text-emerald-400",
              isPending && "bg-zinc-800 text-zinc-500"
            )}>
              <span className={cn(
                "text-base",
                isActive && "animate-bounce"
              )}>
                {stage.icon}
              </span>
              <span className="font-medium">
                {t(stage.id)}
              </span>
              {isActive && stage.id === "extracting" && (
                <span className="text-xs text-blue-400">
                  {completedCount}/{paperCount}
                </span>
              )}
            </div>
            
            {index < stages.length - 1 && (
              <div className={cn(
                "w-8 h-0.5 mx-1 transition-colors duration-300",
                isCompleted ? "bg-emerald-500/50" : "bg-zinc-700"
              )} />
            )}
          </div>
        )
      })}
    </div>
  )
}
