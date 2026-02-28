"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslations } from 'next-intl'
import { AgentConsole } from "@/components/console"
import { Workspace } from "@/components/workspace"
import { ApprovalModal } from "@/components/approval"
import { useResearchStore } from "@/store/research"
import { startResearch, approveResearch, continueResearch, createSSEConnection } from "@/lib/api"
import type { ConversationMessage } from "@/types"

export default function Home() {
  const t = useTranslations('errors')
  const tConsole = useTranslations('console')
  const [showApprovalModal, setShowApprovalModal] = useState(false)
  const [lastQuery, setLastQuery] = useState<string | null>(null)
  const [consoleCollapsed, setConsoleCollapsed] = useState(false)
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
  const selectedModelId = useResearchStore((s) => s.selectedModelId)
  const addMessage = useResearchStore((s) => s.addMessage)
  const clearMessages = useResearchStore((s) => s.clearMessages)
  const startProcessingSimulation = useResearchStore((s) => s.startProcessingSimulation)
  const clearProcessingStates = useResearchStore((s) => s.clearProcessingStates)
  const draft = useResearchStore((s) => s.draft)
  const status = useResearchStore((s) => s.status)
  const isRegenerating = useResearchStore((s) => s.isRegenerating)
  const setIsRegenerating = useResearchStore((s) => s.setIsRegenerating)
  const setTotalCostUsd = useResearchStore((s) => s.setTotalCostUsd)
  const appendStreamingToken = useResearchStore((s) => s.appendStreamingToken)
  const clearStreaming = useResearchStore((s) => s.clearStreaming)

  const prevOutputLanguageRef = useRef(outputLanguage)

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

  useEffect(() => {
    const prev = prevOutputLanguageRef.current
    if (prev === outputLanguage || isRegenerating || !draft || status !== "completed") return

    prevOutputLanguageRef.current = outputLanguage

    const threadId = useResearchStore.getState().threadId
    if (!threadId) return

    const langLabel = outputLanguage === 'en' ? 'English' : '中文'
    const regenerateMsg = `Please regenerate the entire literature review in ${outputLanguage === 'en' ? 'English' : 'Chinese'}. Keep the same structure and citations.`

    setIsRegenerating(true)
    setStatus("continuing")
    addLog("system", tConsole('regenerating', { lang: langLabel }))

    continueResearch(threadId, regenerateMsg, selectedModelId ?? undefined)
      .then(() => {
        if (sseCleanupRef.current) sseCleanupRef.current()
        sseCleanupRef.current = createSSEConnection(
          threadId,
          {
            onMessage: (node, log) => addLog(node, log),
            onCompleted: (data) => {
              clearStreaming()
              if (data.final_draft) {
                setDraft(data.final_draft)
                setCandidatePapers(data.candidate_papers)
                setStatus("completed")
                setIsRegenerating(false)
                addLog("system", "Draft updated successfully!")
              } else {
                setStatus("error")
                setIsRegenerating(false)
                setError(t('draftFailed'))
              }
              sseCleanupRef.current = null
            },
            onError: (error) => {
              clearStreaming()
              setError(error)
              addLog("error", error)
              setIsRegenerating(false)
              sseCleanupRef.current = null
            },
            onCostUpdate: (cost) => setTotalCostUsd(cost),
            onDraftToken: (token) => appendStreamingToken(token),
          },
        )
      })
      .catch((err: unknown) => {
        const errMessage = getErrorMessage(err)
        setError(errMessage)
        addLog("error", errMessage)
        setIsRegenerating(false)
      })
  }, [outputLanguage, draft, status, isRegenerating, setStatus, addLog, setDraft, setCandidatePapers, setError, selectedModelId, getErrorMessage, setIsRegenerating, addMessage, setTotalCostUsd, appendStreamingToken, clearStreaming, t, tConsole])

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
      const response = await startResearch(query, outputLanguage, searchSources, selectedModelId ?? undefined)
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
  }, [reset, clearLogs, clearMessages, setStatus, addLog, addMessage, setThreadId, setCandidatePapers, setError, outputLanguage, searchSources, selectedModelId, getErrorMessage, t])

  const handleApprove = useCallback(async (paperIds: string[]) => {
    const threadId = useResearchStore.getState().threadId
    if (!threadId) return

    setShowApprovalModal(false)
    setStatus("processing")
    addLog("system", `Approved ${paperIds.length} papers. Processing...`)
    
    startProcessingSimulation()

    try {
      await approveResearch(threadId, paperIds)

      const approvedPapers = useResearchStore.getState().candidatePapers.filter(
        (p) => paperIds.includes(p.paper_id)
      )
      setApprovedPapers(approvedPapers)

      if (sseCleanupRef.current) sseCleanupRef.current()
      sseCleanupRef.current = createSSEConnection(
        threadId,
        {
          onMessage: (node, log) => addLog(node, log),
          onCompleted: (data) => {
            clearProcessingStates()
            clearStreaming()
            if (data.final_draft) {
              setDraft(data.final_draft)
              setStatus("completed")
              addLog("system", "Literature review completed!")

              const assistantMessage: ConversationMessage = {
                role: "assistant",
                content: `Generated literature review: "${data.final_draft.title}" with ${data.final_draft.sections.length} sections.`,
                timestamp: new Date().toISOString(),
                metadata: { action: "draft_completed" },
              }
              addMessage(assistantMessage)
            } else {
              setStatus("error")
              setError(t('draftFailed'))
            }
            sseCleanupRef.current = null
          },
          onError: (error) => {
            clearProcessingStates()
            clearStreaming()
            setError(error)
            addLog("error", error)
            sseCleanupRef.current = null
          },
          onCostUpdate: (cost) => setTotalCostUsd(cost),
          onDraftToken: (token) => appendStreamingToken(token),
        },
      )
    } catch (err) {
      clearProcessingStates()
      const message = getErrorMessage(err)
      setError(message)
      addLog("error", message)
    }
  }, [setStatus, addLog, setApprovedPapers, setDraft, setError, addMessage, startProcessingSimulation, clearProcessingStates, setTotalCostUsd, appendStreamingToken, clearStreaming, getErrorMessage, t])

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
      await continueResearch(threadId, message, selectedModelId ?? undefined)

      if (sseCleanupRef.current) sseCleanupRef.current()
      sseCleanupRef.current = createSSEConnection(
        threadId,
        {
          onMessage: (node, log) => addLog(node, log),
          onCompleted: (data) => {
            clearStreaming()
            if (data.final_draft) {
              setDraft(data.final_draft)
              setCandidatePapers(data.candidate_papers)
              setStatus("completed")
              addLog("system", "Draft updated successfully!")

              const assistantMsg: ConversationMessage = {
                role: "assistant",
                content: `Updated draft based on: ${message}`,
                timestamp: new Date().toISOString(),
                metadata: { action: "draft_updated" },
              }
              addMessage(assistantMsg)
            } else {
              setStatus("error")
              setError(t('draftFailed'))
            }
            sseCleanupRef.current = null
          },
          onError: (error) => {
            clearStreaming()
            setError(error)
            addLog("error", error)
            sseCleanupRef.current = null
          },
          onCostUpdate: (cost) => setTotalCostUsd(cost),
          onDraftToken: (token) => appendStreamingToken(token),
        },
      )
    } catch (err) {
      const errMessage = getErrorMessage(err)
      setError(errMessage)
      addLog("error", errMessage)
    }
  }, [setStatus, addLog, addMessage, setDraft, setCandidatePapers, setError, selectedModelId, setTotalCostUsd, appendStreamingToken, clearStreaming, getErrorMessage, t])

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
      <div className={consoleCollapsed ? "w-10 shrink-0" : "w-[30%] min-w-[300px] max-w-[400px]"}>
        <AgentConsole 
          onStartResearch={handleStartResearch} 
          onContinueResearch={handleContinueResearch}
          onNewTopic={handleNewTopic}
          collapsed={consoleCollapsed}
          onToggleCollapse={() => setConsoleCollapsed((c) => !c)}
        />
      </div>
      <div className="flex-1 min-w-0">
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
