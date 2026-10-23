/**
 * Eureka RAG Chatbot — API & UI Type Definitions
 * Matches FastAPI schema in docs/API_CONTRACT.md and docs/openapi.json
 */

export type ChatStatus =
  | 'answered'
  | 'insufficient_evidence'
  | 'out_of_scope'
  | 'temporarily_unavailable'

export interface SourceItem {
  title: string
  url: string
  snippet: string
}

export interface ConversationTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatRequest {
  message: string
  session_id?: string | null
  language?: string
  conversation_history?: ConversationTurn[]
}


export interface ChatResponse {
  request_id: string
  answer: string
  status: ChatStatus
  sources: SourceItem[]
  quick_replies?: string[]
  message?: string | null
}

export interface ErrorDetail {
  field?: string
  issue?: string
}

export interface ApiErrorPayload {
  request_id?: string
  error?: {
    code?: string
    message?: string
    request_id?: string
    details?: ErrorDetail[]
  }
  detail?: string | Array<{ loc?: (string | number)[]; msg?: string; type?: string }>
}

export type ApiResult =
  | {
      success: true
      data: ChatResponse
    }
  | {
      success: false
      errorType:
        | 'validation'
        | 'rate_limit'
        | 'unavailable'
        | 'timeout'
        | 'network'
        | 'schema'
        | 'server'
      message: string
      requestId?: string
      retryAfterSeconds?: number
    }

export interface ChatMessage {
  id: string
  sender: 'user' | 'assistant'
  text: string
  timestamp: number
  status?: ChatStatus
  sources?: SourceItem[]
  quickReplies?: string[]
  requestId?: string
  isError?: boolean
  errorType?: string
  canRetry?: boolean
  failedUserMessage?: string
}

export interface EurekaConfig {
  apiBaseUrl?: string
  initialOpen?: boolean
  theme?: 'light' | 'dark'
  primaryColor?: string
}

declare global {
  interface Window {
    __EUREKA_CONFIG__?: EurekaConfig
    __EUREKA_WIDGET_ACTIVE__?: boolean
  }
}

