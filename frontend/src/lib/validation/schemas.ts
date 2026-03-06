import { z } from "zod"

export const PaperSourceSchema = z.enum(["semantic_scholar", "arxiv", "pubmed"])

export const ModelProviderSchema = z.enum(["openai", "deepseek", "ollama", "custom"])

export const CostTierSchema = z.union([z.literal(1), z.literal(2), z.literal(3)])

export const MessageRoleSchema = z.enum(["user", "assistant", "system"])

export const StructuredContributionSchema = z.object({
  problem: z.string().nullable(),
  method: z.string().nullable(),
  novelty: z.string().nullable(),
  dataset: z.string().nullable(),
  baseline: z.string().nullable(),
  results: z.string().nullable(),
  limitations: z.string().nullable(),
  future_work: z.string().nullable(),
})

export const MethodComparisonEntrySchema = z.object({
  paper_index: z.number().int(),
  title: z.string(),
  method: z.string().nullable(),
  dataset: z.string().nullable(),
  baseline: z.string().nullable(),
  results: z.string().nullable(),
})

export const PaperSchema = z.object({
  paper_id: z.string(),
  title: z.string(),
  authors: z.array(z.string()),
  abstract: z.string(),
  url: z.string(),
  year: z.number().nullable(),
  doi: z.string().nullable(),
  pdf_url: z.string().nullable(),
  pdf_object_key: z.string().nullable().optional(),
  pdf_content_hash: z.string().nullable().optional(),
  pdf_downloaded_at: z.string().datetime().nullable().optional(),
  pdf_size_bytes: z.number().nullable().optional(),
  is_approved: z.boolean().default(false),
  core_contribution: z.string().nullable(),
  structured_contribution: StructuredContributionSchema.nullable(),
  source: PaperSourceSchema.default("semantic_scholar"),
})

export const ConversationMessageSchema = z.object({
  role: MessageRoleSchema,
  content: z.string(),
  timestamp: z.string(),
  metadata: z.record(z.string(), z.unknown()).nullable().optional(),
})

export const ReviewSectionSchema = z.object({
  heading: z.string(),
  content: z.string(),
  cited_paper_ids: z.array(z.string()).default([]),
})

export const DraftOutputSchema = z.object({
  title: z.string(),
  sections: z.array(ReviewSectionSchema),
})

export const StartRequestSchema = z.object({
  query: z.string(),
  language: z.enum(["en", "zh"]),
  sources: z.array(PaperSourceSchema).optional(),
  model_id: z.string().nullable().optional(),
})

export const StartResponseSchema = z.object({
  thread_id: z.string(),
  candidate_papers: z.array(PaperSchema),
  logs: z.array(z.string()),
})

export const ApproveRequestSchema = z.object({
  thread_id: z.string(),
  paper_ids: z.array(z.string()),
})

export const ApproveResponseSchema = z.object({
  thread_id: z.string(),
  final_draft: DraftOutputSchema.nullable().optional(),
  approved_count: z.number(),
  logs: z.array(z.string()).optional(),
})

export const ContinueRequestSchema = z.object({
  thread_id: z.string(),
  message: z.string(),
  model_id: z.string().nullable().optional(),
})

export const ContinueResponseSchema = z.object({
  thread_id: z.string(),
  message: ConversationMessageSchema.optional(),
  final_draft: DraftOutputSchema.nullable().optional(),
  candidate_papers: z.array(PaperSchema).optional(),
  logs: z.array(z.string()).optional(),
})

export const SessionSummarySchema = z.object({
  thread_id: z.string(),
  user_query: z.string(),
  status: z.string(),
  paper_count: z.number(),
  has_draft: z.boolean(),
  created_at: z.string().nullable().optional(),
})

export const SessionDetailSchema = z.object({
  thread_id: z.string(),
  user_query: z.string(),
  status: z.string(),
  candidate_papers: z.array(PaperSchema),
  approved_papers: z.array(PaperSchema),
  final_draft: DraftOutputSchema.nullable(),
  logs: z.array(z.string()),
  messages: z.array(ConversationMessageSchema).default([]),
})

export const ModelConfigSchema = z.object({
  id: z.string(),
  provider: ModelProviderSchema,
  model_name: z.string(),
  display_name: z.string(),
  api_base: z.string(),
  api_key_env: z.string().default("LLM_API_KEY"),
  supports_json_mode: z.boolean().default(true),
  supports_structured_output: z.boolean().default(true),
  max_output_tokens: z.number().int().default(8192),
  is_local: z.boolean().default(false),
  enabled: z.boolean().default(true),
  max_context_tokens: z.number().int().default(128000),
  supports_long_context: z.boolean().default(true),
  cost_tier: CostTierSchema.optional(),
  reasoning_score: z.number().int().min(1).max(10).optional(),
  creativity_score: z.number().int().min(1).max(10).optional(),
  latency_score: z.number().int().min(1).max(10).optional(),
  fallback_for: z.string().nullable().optional(),
})

export type PaperSource = z.infer<typeof PaperSourceSchema>
export type ModelProvider = z.infer<typeof ModelProviderSchema>
export type CostTier = z.infer<typeof CostTierSchema>
export type StructuredContribution = z.infer<typeof StructuredContributionSchema>
export type MethodComparisonEntry = z.infer<typeof MethodComparisonEntrySchema>
export type Paper = z.infer<typeof PaperSchema>
export type ConversationMessage = z.infer<typeof ConversationMessageSchema>
export type ReviewSection = z.infer<typeof ReviewSectionSchema>
export type DraftOutput = z.infer<typeof DraftOutputSchema>
export type StartRequest = z.infer<typeof StartRequestSchema>
export type StartResponse = z.infer<typeof StartResponseSchema>
export type ApproveRequest = z.infer<typeof ApproveRequestSchema>
export type ApproveResponse = z.infer<typeof ApproveResponseSchema>
export type ContinueRequest = z.infer<typeof ContinueRequestSchema>
export type ContinueResponse = z.infer<typeof ContinueResponseSchema>
export type SessionSummary = z.infer<typeof SessionSummarySchema>
export type SessionDetail = z.infer<typeof SessionDetailSchema>
export type ModelConfig = z.infer<typeof ModelConfigSchema>
