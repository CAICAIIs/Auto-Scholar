"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslations } from 'next-intl'
import { AgentConsole } from "@/components/console"
import { Workspace } from "@/components/workspace"
import { ApprovalModal } from "@/components/approval"
import { useResearchStore } from "@/store/research"
import { startResearch, approveResearch, continueResearch } from "@/lib/api"
import type { ConversationMessage } from "@/types"

export default function Home() {
  const t = useTranslations('errors')
  const [showApprovalModal, setShowApprovalModal] = useState(false)
  const [lastQuery, setLastQuery] = useState<string | null>(null)
  const sseCleanupRef = useRef<(() => void) | null>(null)

  const setThreadId = useResearchStore((s) => s.setThreadId)
  const setStatus = useResearchStore((s) => s.setStatus)
  const addLog = useResearchStore((s) => s.addLog)
  const clearLogs = useResearchStore((s) => s.clearLogs)
  const setCandidatePapers = useResearchStore((s) => s.setCandidatePapers)
  const setApprovedPapers = useResearchStore((s) => s.setApprovedPapers)
  const setDraft = useResearchStore((s) => s.setDraft)
  const setError = useResearchStore((s) => s.setError)
  const reset = useResearchStore((s) => s.reset)
  const outputLanguage = useResearchStore((s) => s.outputLanguage)
  const searchSources = useResearchStore((s) => s.searchSources)
  const addMessage = useResearchStore((s) => s.addMessage)
  const clearMessages = useResearchStore((s) => s.clearMessages)
  const startProcessingSimulation = useResearchStore((s) => s.startProcessingSimulation)
  const clearProcessingStates = useResearchStore((s) => s.clearProcessingStates)

  useEffect(() => {
    const cleanup = sseCleanupRef.current
    return () => {
      if (cleanup) {
        cleanup()
      }
    }
  }, [])

  const getErrorMessage = useCallback((err: unknown): string => {
    if (err instanceof Error) {
      const msg = err.message.toLowerCase()
      const originalMsg = err.message
      
      if (msg.includes('timeout') || msg.includes('超时')) {
        return `${t('timeout')} (${originalMsg})`
      }
      if (msg.includes('network') || msg.includes('fetch') || msg.includes('connection')) {
        return `${t('networkError')} (${originalMsg})`
      }
      return `${t('unknownError')} (${originalMsg})`
    }
    return t('unknownError')
  }, [t])

  const handleStartResearch = useCallback(async (query: string) => {
    reset()
    clearLogs()
    clearMessages()
    setStatus("searching")
    setLastQuery(query)
    addLog("system", `Starting research: "${query}"`)

    const userMessage: ConversationMessage = {
      role: "user",
      content: query,
      timestamp: new Date().toISOString(),
      metadata: { action: "start_research" },
    }
    addMessage(userMessage)

    try {
      const response = await startResearch(query, outputLanguage, searchSources)
      setThreadId(response.thread_id)
      setCandidatePapers(response.candidate_papers)

      response.logs.forEach((log) => addLog("workflow", log))

      if (response.candidate_papers.length > 0) {
        setStatus("waiting_approval")
        addLog("system", `Found ${response.candidate_papers.length} papers. Waiting for approval...`)
        setShowApprovalModal(true)
      } else {
        setStatus("error")
        setError(t('noPapers'))
      }
    } catch (err) {
      const message = getErrorMessage(err)
      setError(message)
      addLog("error", message)
    }
  }, [reset, clearLogs, clearMessages, setStatus, addLog, addMessage, setThreadId, setCandidatePapers, setError, outputLanguage, searchSources, getErrorMessage, t])

  const handleApprove = useCallback(async (paperIds: string[]) => {
    const threadId = useResearchStore.getState().threadId
    if (!threadId) return

    setShowApprovalModal(false)
    setStatus("processing")
    addLog("system", `Approved ${paperIds.length} papers. Processing...`)
    
    startProcessingSimulation()

    try {
      const response = await approveResearch(threadId, paperIds)

      response.logs.forEach((log) => addLog("workflow", log))

      const approvedPapers = useResearchStore.getState().candidatePapers.filter(
        (p) => paperIds.includes(p.paper_id)
      )
      setApprovedPapers(approvedPapers)
      clearProcessingStates()

      if (response.final_draft) {
        setDraft(response.final_draft)
        setStatus("completed")
        addLog("system", "Literature review completed!")

        const assistantMessage: ConversationMessage = {
          role: "assistant",
          content: `Generated literature review: "${response.final_draft.title}" with ${response.final_draft.sections.length} sections.`,
          timestamp: new Date().toISOString(),
          metadata: { action: "draft_completed" },
        }
        addMessage(assistantMessage)
      } else {
        setStatus("error")
        setError(t('draftFailed'))
      }
    } catch (err) {
      clearProcessingStates()
      const message = getErrorMessage(err)
      setError(message)
      addLog("error", message)
    }
  }, [setStatus, addLog, setApprovedPapers, setDraft, setError, addMessage, startProcessingSimulation, clearProcessingStates, getErrorMessage, t])

  const handleContinueResearch = useCallback(async (message: string) => {
    const threadId = useResearchStore.getState().threadId
    if (!threadId) return

    setStatus("continuing")
    addLog("system", `Continuing research: "${message}"`)

    const userMessage: ConversationMessage = {
      role: "user",
      content: message,
      timestamp: new Date().toISOString(),
      metadata: { action: "continue_research" },
    }
    addMessage(userMessage)

    try {
      const response = await continueResearch(threadId, message)

      response.logs.forEach((log: string) => addLog("workflow", log))

      if (response.final_draft) {
        setDraft(response.final_draft)
        setCandidatePapers(response.candidate_papers)
        setStatus("completed")
        addLog("system", "Draft updated successfully!")

        addMessage(response.message)
      } else {
        setStatus("error")
        setError(t('draftFailed'))
      }
    } catch (err) {
      const message = getErrorMessage(err)
      setError(message)
      addLog("error", message)
    }
  }, [setStatus, addLog, addMessage, setDraft, setCandidatePapers, setError, getErrorMessage, t])

  const handleRetry = useCallback(() => {
    if (lastQuery) {
      handleStartResearch(lastQuery)
    }
  }, [lastQuery, handleStartResearch])

  const handleCancelApproval = useCallback(() => {
    setShowApprovalModal(false)
    setStatus("idle")
    addLog("system", "Research cancelled by user")
  }, [setStatus, addLog])

  const handleNewTopic = useCallback(() => {
    reset()
    clearLogs()
    clearMessages()
    setLastQuery(null)
  }, [reset, clearLogs, clearMessages])

  return (
    <div className="flex h-screen">
      <div className="w-[30%] min-w-[300px] max-w-[400px]">
        <AgentConsole 
          onStartResearch={handleStartResearch} 
          onContinueResearch={handleContinueResearch}
          onNewTopic={handleNewTopic}
        />
      </div>
      <div className="flex-1">
        <Workspace onRetry={lastQuery ? handleRetry : undefined} />
      </div>
      <ApprovalModal 
        open={showApprovalModal} 
        onApprove={handleApprove} 
        onCancel={handleCancelApproval}
      />
    </div>
  )
}
