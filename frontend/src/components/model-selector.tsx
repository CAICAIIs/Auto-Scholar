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
    <div className="flex items-center gap-1.5">
      <select
        value={selectedModelId ?? ""}
        onChange={(e) => setSelectedModelId(e.target.value || null)}
        disabled={isLoading}
        aria-label={t("model")}
        className="text-xs bg-zinc-800 border border-zinc-700 text-zinc-300 rounded px-1.5 py-0.5 focus:outline-none focus:border-zinc-500 disabled:opacity-50 disabled:cursor-not-allowed max-w-[140px] truncate"
      >
        {availableModels.map((model) => (
          <option key={model.id} value={model.id}>
            {model.display_name}
            {model.is_local ? ` [${t("modelLocal")}]` : ""}
          </option>
        ))}
      </select>
    </div>
  )
}
