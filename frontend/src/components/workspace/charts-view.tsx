"use client"

import { useState, useEffect } from "react"
import { useTranslations } from 'next-intl'
import { Button } from "@/components/ui/button"
import { getCharts, type ChartsResponse } from "@/lib/api/client"
import type { Paper } from "@/types"

interface ChartsViewProps {
  papers: Paper[]
}

export function ChartsView({ papers }: ChartsViewProps) {
  const t = useTranslations('workspace')
  const [charts, setCharts] = useState<ChartsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)

  const loadCharts = async () => {
    if (papers.length === 0) return
    
    setLoading(true)
    setError(null)
    try {
      const data = await getCharts(papers)
      setCharts(data)
      setExpanded(true)
    } catch (err) {
      setError("Failed to generate charts")
      console.error("Charts error:", err)
    } finally {
      setLoading(false)
    }
  }

  if (papers.length === 0) {
    return null
  }

  return (
    <div className="border-t border-zinc-200 dark:border-zinc-700 mt-8 pt-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          {t('chartsTitle')}
        </h3>
        <Button
          variant="outline"
          size="sm"
          onClick={loadCharts}
          disabled={loading}
        >
          {loading ? "..." : expanded ? t('chartsRefresh') : t('chartsGenerate')}
        </Button>
      </div>

      {error && (
        <p className="text-sm text-red-500 mb-4">{error}</p>
      )}

      {expanded && charts && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {charts.year_trend && (
            <div className="bg-zinc-50 dark:bg-zinc-800 rounded-lg p-4">
              <h4 className="text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-3">
                {t('chartYearTrend')}
              </h4>
              <img
                src={`data:image/png;base64,${charts.year_trend}`}
                alt="Year Trend Chart"
                className="w-full rounded"
              />
            </div>
          )}

          {charts.source_distribution && (
            <div className="bg-zinc-50 dark:bg-zinc-800 rounded-lg p-4">
              <h4 className="text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-3">
                {t('chartSourceDistribution')}
              </h4>
              <img
                src={`data:image/png;base64,${charts.source_distribution}`}
                alt="Source Distribution Chart"
                className="w-full rounded"
              />
            </div>
          )}

          {charts.author_frequency && (
            <div className="bg-zinc-50 dark:bg-zinc-800 rounded-lg p-4 md:col-span-2">
              <h4 className="text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-3">
                {t('chartAuthorFrequency')}
              </h4>
              <img
                src={`data:image/png;base64,${charts.author_frequency}`}
                alt="Author Frequency Chart"
                className="w-full rounded"
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
