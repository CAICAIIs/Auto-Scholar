"use client"

import { useState } from "react"
import { ApprovalModal } from "@/components/approval"
import { AgentConsole } from "@/components/console"
import { ErrorBoundary } from "@/components/error-boundary"
import { Workspace } from "@/components/workspace"
import { useResearchWorkflow } from "@/hooks"

export default function Home() {
  const [consoleCollapsed, setConsoleCollapsed] = useState(false)
  const {
    showApprovalModal,
    lastQuery,
    handleApprove,
    handleCancelApproval,
    handleContinueResearch,
    handleNewTopic,
    handleRetry,
    handleStartResearch,
  } = useResearchWorkflow()

  return (
    <div className="flex h-screen">
      <div className={consoleCollapsed ? "w-10 shrink-0" : "w-[30%] min-w-[300px] max-w-[400px]"}>
        <ErrorBoundary>
          <AgentConsole
            onStartResearch={handleStartResearch}
            onContinueResearch={handleContinueResearch}
            onNewTopic={handleNewTopic}
            collapsed={consoleCollapsed}
            onToggleCollapse={() => setConsoleCollapsed((collapsed) => !collapsed)}
          />
        </ErrorBoundary>
      </div>
      <div className="flex-1 min-w-0">
        <ErrorBoundary>
          <Workspace onRetry={lastQuery ? handleRetry : undefined} />
        </ErrorBoundary>
      </div>
      <ApprovalModal
        open={showApprovalModal}
        onApprove={handleApprove}
        onCancel={handleCancelApproval}
      />
    </div>
  )
}
