import type {
  ApproveRequest as ApiApproveRequest,
  ApproveResponse as ApiApproveResponse,
  ContinueRequest as ApiContinueRequest,
  ContinueResponse as ApiContinueResponse,
  StartRequest as ApiStartRequest,
} from "@/lib/validation/schemas"

export type {
  ApproveResponse as FullApproveResponse,
  ContinueResponse as FullContinueResponse,
  ConversationMessage,
  CostTier,
  DraftOutput,
  MethodComparisonEntry,
  ModelConfig,
  ModelProvider,
  Paper,
  PaperSource,
  ReviewSection,
  SessionDetail,
  SessionSummary,
  StartResponse,
  StructuredContribution,
} from "@/lib/validation/schemas"

export type StartRequest = ApiStartRequest
export type ApproveRequest = ApiApproveRequest
export type ContinueRequest = ApiContinueRequest
export type ApproveResponse = Pick<ApiApproveResponse, "thread_id" | "approved_count">
export type ContinueResponse = Pick<ApiContinueResponse, "thread_id">

export interface StatusResponse {
  thread_id: string
  next_nodes: string[]
  logs: string[]
  has_draft: boolean
  candidate_count: number
  approved_count: number
}

export type StreamEventType = "log" | "interrupt" | "draft_update" | "done" | "error"

export interface StreamEvent {
  type: StreamEventType
  node?: string
  log?: string
  data?: unknown
  detail?: string
}
