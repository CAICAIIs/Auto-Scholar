"use client"

import { useState } from "react"
import { useResearchStore } from "@/store/research"
import { ReviewRenderer } from "./review-renderer"
import { StreamingDraftViewer } from "./streaming-draft-viewer"
import { ChartsView } from "./charts-view"
import { MethodComparisonTable } from "./method-comparison-table"
import { StructuredSummaryList } from "./structured-summary"
import { ProcessingVisualizer } from "./processing-visualizer"
import { useTranslations } from 'next-intl'
import { Button } from "@/components/ui/button"
import { exportReview, type ExportFormat, type CitationStyle } from "@/lib/api/client"

interface WorkspaceProps {
  onRetry?: () => void
}

const CITATION_STYLES: { id: CitationStyle; label: string }[] = [
  { id: "apa", label: "APA" },
  { id: "mla", label: "MLA" },
  { id: "ieee", label: "IEEE" },
  { id: "gb-t7714", label: "GB/T 7714" },
]

export function Workspace({ onRetry }: WorkspaceProps) {
  const t = useTranslations('workspace')
  const tErrors = useTranslations('errors')
  const draft = useResearchStore((s) => s.draft)
  const editedDraft = useResearchStore((s) => s.editedDraft)
  const approvedPapers = useResearchStore((s) => s.approvedPapers)
  const status = useResearchStore((s) => s.status)
  const error = useResearchStore((s) => s.error)
  const isEditing = useResearchStore((s) => s.isEditing)
  const setIsEditing = useResearchStore((s) => s.setIsEditing)
  const resetToOriginal = useResearchStore((s) => s.resetToOriginal)
  const selectedPaperIds = useResearchStore((s) => s.selectedPaperIds)
  const isStreaming = useResearchStore((s) => s.isStreaming)
  const streamingText = useResearchStore((s) => s.streamingText)

  const [showExportDialog, setShowExportDialog] = useState(false)
  const [exportFormat, setExportFormat] = useState<ExportFormat>("markdown")
  const [citationStyle, setCitationStyle] = useState<CitationStyle>("apa")
  const [isExporting, setIsExporting] = useState(false)

  const displayDraft = editedDraft || draft
  const isProcessing = status === "processing" || status === "drafting" || status === "continuing"
  const hasSelectedPapers = selectedPaperIds.size > 0

  if (!displayDraft) {
    if ((isStreaming || streamingText) && isProcessing) {
      return (
        <div className="h-full overflow-y-auto bg-white dark:bg-zinc-900">
          <div className="p-8">
            <div className="max-w-3xl mx-auto">
              <StreamingDraftViewer />
            </div>
          </div>
        </div>
      )
    }

    if (isProcessing && hasSelectedPapers) {
      return (
        <div className="h-full p-6 bg-zinc-950">
          <ProcessingVisualizer />
        </div>
      )
    }

    return (
      <div className="flex h-full items-center justify-center bg-zinc-50 dark:bg-zinc-900">
        <div className="text-center max-w-md px-4">
          <h2 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
            {t('title')}
          </h2>
          <p className="mt-2 text-zinc-500 dark:text-zinc-400">
            {status === "idle"
              ? t('idle')
              : status === "error"
              ? (error || t('error'))
              : t('processing')}
          </p>
          {status === "error" && onRetry && (
            <Button
              variant="outline"
              size="sm"
              onClick={onRetry}
              className="mt-4"
            >
              {tErrors('retry')}
            </Button>
          )}
        </div>
      </div>
    )
  }

  const handleReset = () => {
    if (window.confirm(t('resetConfirm'))) {
      resetToOriginal()
    }
  }

  const handleExport = async () => {
    if (!displayDraft) return
    setIsExporting(true)
    try {
      const blob = await exportReview(displayDraft, approvedPapers, exportFormat, citationStyle)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = exportFormat === "markdown" ? "review.md" : "review.docx"
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      setShowExportDialog(false)
    } catch (err) {
      console.error("Export failed:", err)
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-white dark:bg-zinc-900">
      <div className="sticky top-0 z-10 bg-white dark:bg-zinc-900 border-b border-zinc-200 dark:border-zinc-700 px-8 py-3">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Button
              variant={isEditing ? "default" : "outline"}
              size="sm"
              onClick={() => setIsEditing(!isEditing)}
            >
              {isEditing ? t('preview') : t('edit')}
            </Button>
            {isEditing && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleReset}
              >
                {t('reset')}
              </Button>
            )}
          </div>
          <div className="flex items-center gap-2">
            {isEditing && (
              <span className="text-xs text-zinc-500 mr-2">{t('editing')}</span>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowExportDialog(true)}
            >
              {t('export')}
            </Button>
          </div>
        </div>
      </div>
      <div className="p-8">
        <div className="max-w-3xl mx-auto">
          <ReviewRenderer 
            draft={displayDraft} 
            papers={approvedPapers} 
            isEditing={isEditing}
          />
          <MethodComparisonTable papers={approvedPapers} />
          <StructuredSummaryList papers={approvedPapers} />
          <ChartsView papers={approvedPapers} />
        </div>
      </div>

      {showExportDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-zinc-800 rounded-lg shadow-xl p-6 w-full max-w-md mx-4">
            <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 mb-2">
              {t('exportTitle')}
            </h3>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-4">
              {t('exportDescription')}
            </p>
            
            <div className="mb-4">
              <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('exportFormatLabel')}
              </p>
              <div className="space-y-2">
                <label className="flex items-center gap-3 p-3 rounded-md border border-zinc-200 dark:border-zinc-600 cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-700">
                  <input
                    type="radio"
                    name="format"
                    value="markdown"
                    checked={exportFormat === "markdown"}
                    onChange={() => setExportFormat("markdown")}
                    className="w-4 h-4"
                  />
                  <span className="text-zinc-900 dark:text-zinc-100">{t('exportMarkdown')}</span>
                </label>
                <label className="flex items-center gap-3 p-3 rounded-md border border-zinc-200 dark:border-zinc-600 cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-700">
                  <input
                    type="radio"
                    name="format"
                    value="docx"
                    checked={exportFormat === "docx"}
                    onChange={() => setExportFormat("docx")}
                    className="w-4 h-4"
                  />
                  <span className="text-zinc-900 dark:text-zinc-100">{t('exportWord')}</span>
                </label>
              </div>
            </div>

            <div className="mb-6">
              <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('citationStyleLabel')}
              </p>
              <div className="grid grid-cols-2 gap-2">
                {CITATION_STYLES.map((style) => (
                  <label
                    key={style.id}
                    className={`flex items-center justify-center p-2 rounded-md border cursor-pointer transition-colors ${
                      citationStyle === style.id
                        ? "border-blue-500 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300"
                        : "border-zinc-200 dark:border-zinc-600 hover:bg-zinc-50 dark:hover:bg-zinc-700 text-zinc-900 dark:text-zinc-100"
                    }`}
                  >
                    <input
                      type="radio"
                      name="citationStyle"
                      value={style.id}
                      checked={citationStyle === style.id}
                      onChange={() => setCitationStyle(style.id)}
                      className="sr-only"
                    />
                    <span className="text-sm font-medium">{style.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <Button
                variant="ghost"
                onClick={() => setShowExportDialog(false)}
                disabled={isExporting}
              >
                {t('exportCancel')}
              </Button>
              <Button
                onClick={handleExport}
                disabled={isExporting}
              >
                {isExporting ? "..." : t('exportDownload')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
