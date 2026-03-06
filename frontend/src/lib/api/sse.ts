import type { DraftOutput, Paper } from "@/types"

export type SSEConnectionState = "connecting" | "connected" | "error" | "closed"

export interface SSELogEvent {
  node: string
  log: string
}

export interface SSEDoneEvent {
  event: "done" | "completed"
  final_draft?: DraftOutput | null
  candidate_papers?: Paper[]
}

export interface SSEErrorEvent {
  event: "error"
  detail?: string
}

export interface SSECostUpdateEvent {
  event: "cost_update"
  node?: string
  total_cost_usd: number
}

export interface SSEDraftTokenEvent {
  event: "draft_token"
  token: string
}

export interface SSEResearchPlanEvent {
  event: "research_plan"
  research_plan: unknown
}

export interface SSERelfectionEvent {
  event: "reflection"
  reflection: unknown
}

export type SSEEvent =
  | SSELogEvent
  | SSEDoneEvent
  | SSEErrorEvent
  | SSECostUpdateEvent
  | SSEDraftTokenEvent
  | SSEResearchPlanEvent
  | SSERelfectionEvent

export interface SSECompletedData {
  final_draft: DraftOutput | null
  candidate_papers: Paper[]
}

export interface SSECallbacks {
  onMessage: (node: string, log: string) => void
  onCompleted: (data: SSECompletedData) => void
  onError: (error: string) => void
  onCostUpdate?: (totalCostUsd: number) => void
  onDraftToken?: (token: string) => void
}

export function parseSSELines(raw: string): string[] {
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
}

export function parseSSEEventLine(line: string): SSEEvent | null {
  try {
    return JSON.parse(line) as SSEEvent
  } catch {
    return null
  }
}
