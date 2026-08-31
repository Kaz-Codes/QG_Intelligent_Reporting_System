// Mirrors backend/api/chatbot.py's ChatResponse (the chatbot backend, a
// separate FastAPI service from this app's own app/ backend — see
// src/lib/chatbot/api.ts for the base URL it talks to).

export interface ChartSpec {
  type: 'bar' | 'line' | 'pie' | 'none' | string
  x?: string
  y?: string[]
  title?: string
  /** A chart can carry its own data (e.g. a forecast = history + projected
   * points, which are not in the message's SQL rows). Falls back to the
   * message's rows when absent. */
  data?: Record<string, unknown>[]
}

export interface ForecastResult {
  ok?: boolean
  method?: string
  direction?: string
  confidence?: string
  r_squared?: number
  projections?: unknown
  [key: string]: unknown
}

export interface ChatResponse {
  thread_id: string
  answer: string
  route: string
  intent: string
  domain: string
  clarification_options: string[]
  columns: string[]
  rows: Record<string, unknown>[]
  row_count: number
  charts: ChartSpec[]
  sql: string
  tables_used: string[]
  knowledge_inferred: boolean
  analysis_type: string
  forecast: ForecastResult | null
  forecast_skipped_reason: string
  computation_code: string
  computation_explanation: string
  computation_result: unknown
  error: string
}

export type StreamEvent =
  | { type: 'start'; thread_id: string }
  | { type: 'status'; node: string; label: string }
  | { type: 'token'; text: string }
  | { type: 'error'; message: string }
  | ({ type: 'done'; streamed: boolean } & ChatResponse)

export interface ChatHistoryMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatHistory {
  thread_id: string
  messages: ChatHistoryMessage[]
}

export interface HealthResponse {
  status: string
  database: 'up' | 'down' | string
  warm: boolean
}

/** One turn in the Assistant page's conversation. */
export interface AssistantMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  failed?: boolean
  clarificationOptions?: string[]
  columns?: string[]
  rows?: Record<string, unknown>[]
  charts?: ChartSpec[]
  meta?: {
    route?: string
    domain?: string
    intent?: string
    rowCount?: number
    sql?: string
    tablesUsed?: string[]
    knowledgeInferred?: boolean
    analysisType?: string
    forecast?: ForecastResult | null
    computationCode?: string
    computationExplanation?: string
    computationResult?: unknown
    error?: string
  }
}


/** One row in the conversation sidebar. Titles and counts only - the messages
 *  payload is deliberately not sent by GET /chatbot/conversations, because a
 *  stored conversation carries every table the assistant ever returned. */
export interface ConversationSummary {
  thread_id: string
  title: string
  message_count: number
  updated_at: string
  created_at: string
}

/** One past conversation, opened from the sidebar. */
export interface ConversationDetail {
  thread_id: string
  title: string
  messages: AssistantMessage[]
  updated_at: string
  created_at: string
}
