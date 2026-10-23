/**
 * Eureka RAG Chatbot API Client
 * Robust, typed client for POST /api/v1/chat with schema validation,
 * abort handling, safe citation sanitization, and fallback mock support.
 */
import type {
  ApiErrorPayload,
  ApiResult,
  ChatRequest,
  ChatResponse,
  ChatStatus,
} from './types'
import { mockChatApi } from './mockApi'
import { filterSafeSources } from './urlValidator'

const VALID_STATUSES = new Set<ChatStatus>([
  'answered',
  'insufficient_evidence',
  'out_of_scope',
  'temporarily_unavailable',
])

export interface ChatClientOptions {
  baseUrl?: string
  mockMode?: boolean
  timeoutMs?: number
  signal?: AbortSignal
}

/**
 * Returns the resolved API base URL from runtime config, Vite environment, or default.
 */
export function getApiBaseUrl(): string {
  // 1. Runtime window configuration (used when embedded into host site layout)
  if (typeof window !== 'undefined' && window.__EUREKA_CONFIG__?.apiBaseUrl) {
    const runtimeUrl = window.__EUREKA_CONFIG__.apiBaseUrl.trim()
    if (runtimeUrl.length > 0) {
      return runtimeUrl.replace(/\/+$/, '')
    }
  }

  // 2. Build-time Vite environment variable
  const envUrl = import.meta.env.VITE_EUREKA_API_BASE_URL
  if (typeof envUrl === 'string') {
    const trimmed = envUrl.trim().replace(/\/+$/, '')
    // In dev mode only: if accessing via external tunnel/LAN IP and env points to localhost,
    // return empty string so requests use relative URLs through the Vite dev proxy.
    if (
      import.meta.env.DEV &&
      typeof window !== 'undefined' &&
      window.location &&
      window.location.hostname &&
      window.location.hostname !== 'localhost' &&
      window.location.hostname !== '127.0.0.1' &&
      (trimmed.includes('localhost') || trimmed.includes('127.0.0.1'))
    ) {
      return ''
    }
    return trimmed
  }

  // 3. Fallback for external tunnel in development
  if (
    typeof window !== 'undefined' &&
    window.location &&
    window.location.hostname &&
    window.location.hostname !== 'localhost' &&
    window.location.hostname !== '127.0.0.1'
  ) {
    return ''
  }

  return 'http://127.0.0.1:8000'
}


/**
 * Checks whether mock mode is enabled via environment variable.
 */
export function isMockModeEnabled(): boolean {
  return import.meta.env.VITE_MOCK_API === 'true'
}

/**
 * Validates request payload according to the API contract.
 */
export function validateChatRequest(request: ChatRequest): string | null {
  if (!request || typeof request.message !== 'string') {
    return 'Question cannot be empty.'
  }

  const trimmed = request.message.trim()
  if (trimmed.length === 0) {
    return 'Please enter a question before sending.'
  }

  if (trimmed.length > 2000) {
    return `Question exceeds the 2,000-character maximum limit (${trimmed.length} characters).`
  }

  return null
}

/**
 * Sends a chat query to the backend API.
 */
export async function sendChatMessage(
  request: ChatRequest,
  options: ChatClientOptions = {}
): Promise<ApiResult> {
  // 1. Client-side input validation
  const validationError = validateChatRequest(request)
  if (validationError) {
    return {
      success: false,
      errorType: 'validation',
      message: validationError,
    }
  }

  const useMock = options.mockMode ?? isMockModeEnabled()
  if (useMock) {
    return mockChatApi(request)
  }

  const baseUrl = (options.baseUrl ?? getApiBaseUrl()).replace(/\/+$/, '')
  const endpoint = `${baseUrl}/api/v1/chat`
  const timeoutMs = options.timeoutMs ?? 30000

  const controller = new AbortController()
  let isTimedOut = false

  const timer = setTimeout(() => {
    isTimedOut = true
    controller.abort()
  }, timeoutMs)

  // Listen to external signal if provided
  if (options.signal) {
    options.signal.addEventListener('abort', () => {
      controller.abort()
    })
  }

  try {
    const payload: ChatRequest = {
      message: request.message.trim(),
      session_id: request.session_id ?? null,
      language: request.language ?? 'auto',
      conversation_history: request.conversation_history ?? undefined,
    }


    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })

    clearTimeout(timer)

    const requestIdHeader = response.headers.get('x-request-id') ?? undefined

    // 2. Handle HTTP 429 Rate Limit
    if (response.status === 429) {
      const retryAfterHeader = response.headers.get('retry-after')
      const retryAfter = retryAfterHeader ? parseInt(retryAfterHeader, 10) : 60
      return {
        success: false,
        errorType: 'rate_limit',
        message: 'Too many requests. Please wait a moment before asking another question.',
        requestId: requestIdHeader,
        retryAfterSeconds: isNaN(retryAfter) ? 60 : retryAfter,
      }
    }

    // 3. Parse JSON response safely
    let responseBody: unknown
    try {
      responseBody = await response.json()
    } catch {
      return {
        success: false,
        errorType: 'schema',
        message: 'Failed to read response from server.',
        requestId: requestIdHeader,
      }
    }

    // 4. Handle HTTP 503 / Service Unavailable
    if (response.status === 503) {
      const errorData = responseBody as ApiErrorPayload
      const msg =
        typeof errorData?.error?.message === 'string'
          ? errorData.error.message
          : 'The Ask Eureka AI service is temporarily unavailable. Please try again in a few moments.'
      return {
        success: false,
        errorType: 'unavailable',
        message: msg,
        requestId: errorData?.request_id ?? requestIdHeader,
      }
    }

    // 5. Handle HTTP 422 Validation Error
    if (response.status === 422) {
      const errorData = responseBody as ApiErrorPayload
      let detailMsg = 'Invalid request payload.'
      if (typeof errorData?.detail === 'string') {
        detailMsg = errorData.detail
      } else if (Array.isArray(errorData?.detail) && errorData.detail.length > 0) {
        detailMsg = errorData.detail.map((d) => d.msg || 'Constraint error').join('; ')
      }
      return {
        success: false,
        errorType: 'validation',
        message: detailMsg,
        requestId: requestIdHeader,
      }
    }

    // 6. Handle HTTP 200 OK
    if (response.ok) {
      const data = responseBody as Record<string, unknown>

      // Validate required response fields
      if (
        typeof data.request_id !== 'string' ||
        typeof data.answer !== 'string' ||
        typeof data.status !== 'string' ||
        !VALID_STATUSES.has(data.status as ChatStatus)
      ) {
        return {
          success: false,
          errorType: 'schema',
          message: 'Received an invalid response format from the chatbot service.',
          requestId: requestIdHeader,
        }
      }

      // Filter and sanitize citation URLs
      const safeSources = filterSafeSources(data.sources)

      const chatResponse: ChatResponse = {
        request_id: data.request_id,
        answer: data.answer,
        status: data.status as ChatStatus,
        sources: safeSources,
        quick_replies: Array.isArray(data.quick_replies)
          ? data.quick_replies.filter((q): q is string => typeof q === 'string')
          : [],
        message: typeof data.message === 'string' ? data.message : null,
      }

      return {
        success: true,
        data: chatResponse,
      }
    }

    // 7. Generic error handling for other status codes
    const errorData = responseBody as ApiErrorPayload
    return {
      success: false,
      errorType: 'server',
      message:
        typeof errorData?.error?.message === 'string'
          ? errorData.error.message
          : `Chat service responded with HTTP status ${response.status}.`,
      requestId: errorData?.request_id ?? requestIdHeader,
    }
  } catch (err: unknown) {
    clearTimeout(timer)

    if (isTimedOut) {
      return {
        success: false,
        errorType: 'timeout',
        message: 'The request timed out. Please check your connection and try again.',
      }
    }

    if (err instanceof DOMException && err.name === 'AbortError') {
      return {
        success: false,
        errorType: 'network',
        message: 'Request was cancelled.',
      }
    }

    return {
      success: false,
      errorType: 'network',
      message: 'Network connection error. Please verify your internet connection.',
    }
  }
}
