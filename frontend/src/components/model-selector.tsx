"use client"

import { useEffect, useRef } from "react"
import { useTranslations } from "next-intl"
import { useResearchStore } from "@/store/research"
import { fetchModels } from "@/lib/api"
import type { ModelConfig } from "@/types"

export function ModelSelector() {
  const t = useTranslations("query")
  const availableModels = useResearchStore((s) => s.availableModels)
  const selectedModelId = useResearchStore((s) => s.selectedModelId)
  const setAvailableModels = useResearchStore((s) => s.setAvailableModels)
  const setSelectedModelId = useResearchStore((s) => s.setSelectedModelId)
  const status = useResearchStore((s) => s.status)
  const isLoading = status !== "idle" && status !== "completed" && status !== "error"
  const fetchedRef = useRef(false)

  useEffect(() => {
    if (fetchedRef.current || availableModels.length > 0) return
    fetchedRef.current = true
    let cancelled = false
    fetchModels()
      .then((models: ModelConfig[]) => {
        if (cancelled) return
        setAvailableModels(models)
        const stored = localStorage.getItem("auto-scholar-model")
        if (!stored && models.length > 0) {
          setSelectedModelId(models[0].id)
        }
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [availableModels.length, setAvailableModels, setSelectedModelId])

  if (availableModels.length === 0) {
    return null
  }

  return (
    <div className="flex items-center">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width={14}
        height={14}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-zinc-500 mr-1 shrink-0"
      >
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
        <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
        <line x1="12" y1="22.08" x2="12" y2="12" />
      </svg>
      <select
        value={selectedModelId ?? ""}
        onChange={(e) => setSelectedModelId(e.target.value || null)}
        disabled={isLoading}
        aria-label={t("model")}
        className="text-xs bg-transparent border-none text-zinc-400 hover:text-zinc-100 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed max-w-[120px] truncate cursor-pointer appearance-none pr-3"
      >
        {availableModels.map((model) => (
          <option key={model.id} value={model.id} className="bg-zinc-800 text-zinc-300">
            {model.display_name}
            {model.is_local ? ` [${t("modelLocal")}]` : ""}
            {model.cost_tier ? ` · ${t(`costTier_${model.cost_tier}`)}` : ""}
            {model.fallback_for ? ` → ${model.fallback_for}` : ""}
          </option>
        ))}
      </select>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width={10}
        height={10}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-zinc-500 -ml-2 pointer-events-none"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </div>
  )
}
