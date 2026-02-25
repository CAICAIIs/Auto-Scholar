import type { StartRequest, StartResponse, ApproveRequest, ApproveResponse, StatusResponse, DraftOutput, Paper, SessionSummary, SessionDetail, PaperSource, ContinueRequest, ContinueResponse, ModelConfig } from "@/types"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

const ERROR_MESSAGES: Record<number, string> = {
  504: "研究超时，请缩小搜索范围后重试",
  429: "请求过于频繁，请稍后再试",
  500: "服务器内部错误",
  503: "服务暂时不可用，请稍后重试",
}

function _extractDetail(raw: string): string {
  try {
    const parsed = JSON.parse(raw)
    if (typeof parsed.detail === "string") return parsed.detail
  } catch {
    // not JSON — use raw text
  }
  return raw
}

function getReadableError(status: number, rawBody: string): string {
  const base = ERROR_MESSAGES[status]
  const detail = _extractDetail(rawBody)
  if (base && detail) return `${base}: ${detail}`
  if (base) return base
  return detail || `请求失败 (${status})`
}

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(getReadableError(status, message))
    this.name = "ApiError"
  }
}

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController()

  const timeout = setTimeout(() => {
    controller.abort()
  }, 300000) // 5 minutes timeout for long-running operations

  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    })
    clearTimeout(timeout)

    if (!res.ok && res.status !== 202) {
      const text = await res.text()
      throw new ApiError(res.status, text || `Request failed with status ${res.status}`)
    }

    return res.json()
  } catch (error) {
    clearTimeout(timeout)

    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('请求超时：处理时间过长，请稍后重试或减少批准的论文数量')
    }

    throw error
  }
}

export async function startResearch(
  query: string,
  language: "en" | "zh" = "en",
  sources: PaperSource[] = ["semantic_scholar", "arxiv", "pubmed"],
  modelId?: string
): Promise<StartResponse> {
  const body: StartRequest = { query, language, sources, model_id: modelId }
  return request<StartResponse>("/api/research/start", {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export async function approveResearch(threadId: string, paperIds: string[]): Promise<ApproveResponse> {
  const body: ApproveRequest = { thread_id: threadId, paper_ids: paperIds }
  return request<ApproveResponse>("/api/research/approve", {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export async function continueResearch(threadId: string, message: string, modelId?: string): Promise<ContinueResponse> {
  const body: ContinueRequest = { thread_id: threadId, message, model_id: modelId }
  return request<ContinueResponse>("/api/research/continue", {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export async function getStatus(threadId: string): Promise<StatusResponse> {
  return request<StatusResponse>(`/api/research/status/${threadId}`)
}

export type ExportFormat = "markdown" | "docx"
export type CitationStyle = "apa" | "mla" | "ieee" | "gb-t7714"

export interface ChartsResponse {
  year_trend: string | null
  source_distribution: string | null
  author_frequency: string | null
}

export async function exportReview(
  draft: DraftOutput,
  papers: Paper[],
  format: ExportFormat = "markdown",
  citationStyle: CitationStyle = "apa"
): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/research/export?format=${format}&citation_style=${citationStyle}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ draft, papers }),
  })

  if (!res.ok) {
    const text = await res.text()
    throw new ApiError(res.status, text || `Export failed with status ${res.status}`)
  }

  return res.blob()
}

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

export function createSSEConnection(
  threadId: string,
  callbacks: SSECallbacks
): () => void {
  const eventSource = new EventSource(`${API_BASE}/api/research/stream/${threadId}`)

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      
      if (data.event === "completed") {
        callbacks.onCompleted({
          final_draft: data.final_draft ?? null,
          candidate_papers: data.candidate_papers ?? [],
        })
        eventSource.close()
        return
      }
      
      if (data.event === "error") {
        callbacks.onError(data.detail || "Unknown error")
        eventSource.close()
        return
      }

      if (data.event === "cost_update") {
        callbacks.onCostUpdate?.(data.total_cost_usd)
        return
      }

      if (data.event === "draft_token") {
        callbacks.onDraftToken?.(data.token)
        return
      }
      
      if (data.node && data.log) {
        callbacks.onMessage(data.node, data.log)
      }
    } catch {
      console.error("Failed to parse SSE message:", event.data)
    }
  }

  eventSource.onerror = () => {
    callbacks.onError("Connection lost")
    eventSource.close()
  }

  return () => eventSource.close()
}

export async function listSessions(limit: number = 50): Promise<SessionSummary[]> {
  return request<SessionSummary[]>(`/api/research/sessions?limit=${limit}`)
}

export async function getSession(threadId: string): Promise<SessionDetail> {
  return request<SessionDetail>(`/api/research/sessions/${threadId}`)
}

export async function getCharts(papers: Paper[]): Promise<ChartsResponse> {
  return request<ChartsResponse>("/api/research/charts", {
    method: "POST",
    body: JSON.stringify({ papers }),
  })
}

export async function fetchModels(): Promise<ModelConfig[]> {
  return request<ModelConfig[]>("/api/models")
}

export { ApiError }
