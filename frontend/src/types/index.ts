// Paper metadata from backend
export type PaperSource = "semantic_scholar" | "arxiv" | "pubmed"

export type MessageRole = "user" | "assistant" | "system"

export interface ConversationMessage {
  role: MessageRole
  content: string
  timestamp: string
  metadata?: Record<string, unknown>
}

export interface StructuredContribution {
  problem: string | null
  method: string | null
  novelty: string | null
  dataset: string | null
  baseline: string | null
  results: string | null
  limitations: string | null
  future_work: string | null
}

export interface MethodComparisonEntry {
  paper_index: number
  title: string
  method: string | null
  dataset: string | null
  baseline: string | null
  results: string | null
}

export interface Paper {
  paper_id: string
  title: string
  authors: string[]
  abstract: string
  url: string
  year: number | null
  doi: string | null
  pdf_url: string | null
  is_approved: boolean
  core_contribution: string | null
  structured_contribution: StructuredContribution | null
  source?: PaperSource
}

// Review section with citations
export interface ReviewSection {
  heading: string
  content: string // Contains [1], [2] style inline citations
  cited_paper_ids: string[]
}

// Final draft output
export interface DraftOutput {
  title: string
  sections: ReviewSection[]
}

// SSE event types
export type StreamEventType = "log" | "interrupt" | "draft_update" | "done" | "error"

export interface StreamEvent {
  type: StreamEventType
  node?: string
  log?: string
  data?: unknown
  detail?: string
}

// API request/response types
export interface StartRequest {
  query: string
  language: "en" | "zh"
  sources?: PaperSource[]
}

export interface StartResponse {
  thread_id: string
  candidate_papers: Paper[]
  logs: string[]
}

export interface ApproveRequest {
  thread_id: string
  paper_ids: string[]
}

export interface ApproveResponse {
  thread_id: string
  approved_count: number
}

export interface ContinueRequest {
  thread_id: string
  message: string
}

export interface ContinueResponse {
  thread_id: string
}

export interface StatusResponse {
  thread_id: string
  next_nodes: string[]
  logs: string[]
  has_draft: boolean
  candidate_count: number
  approved_count: number
}

export interface SessionSummary {
  thread_id: string
  user_query: string
  status: "completed" | "in_progress" | "pending"
  paper_count: number
  has_draft: boolean
  created_at?: string
}

export interface SessionDetail {
  thread_id: string
  user_query: string
  status: string
  candidate_papers: Paper[]
  approved_papers: Paper[]
  final_draft: DraftOutput | null
  logs: string[]
  messages: ConversationMessage[]
}
