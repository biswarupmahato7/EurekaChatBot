import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  sendChatMessage,
  validateChatRequest,
  getApiBaseUrl,
} from '../api/chatClient'
import type { ChatRequest } from '../api/types'

describe('chatClient', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  describe('validateChatRequest', () => {
    it('rejects empty or whitespace-only messages', () => {
      expect(validateChatRequest({ message: '' })).not.toBeNull()
      expect(validateChatRequest({ message: '   \n  ' })).not.toBeNull()
    })

    it('accepts valid 1-2000 character messages', () => {
      expect(validateChatRequest({ message: 'What is NetSuite?' })).toBeNull()
      expect(validateChatRequest({ message: 'A'.repeat(2000) })).toBeNull()
    })

    it('rejects messages over 2000 characters', () => {
      const error = validateChatRequest({ message: 'A'.repeat(2001) })
      expect(error).toContain('exceeds the 2,000-character')
    })
  })

  describe('sendChatMessage network calls', () => {
    it('sends POST request to /api/v1/chat with correct schema and parses answered response', async () => {
      const mockResponseData = {
        request_id: 'req-test-1234',
        answer: 'Eureka Solutions provides Oracle NetSuite and cloud data integration.',
        status: 'answered',
        sources: [
          {
            title: 'NetSuite Services',
            url: 'https://eurekasolutions.in/Eureka2026/services/netsuite/',
            snippet: 'NetSuite implementation experts.',
          },
        ],
        message: null,
      }

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'x-request-id': 'req-test-1234' }),
        json: async () => mockResponseData,
      })

      const request: ChatRequest = {
        message: 'What ERP software do you provide?',
        session_id: 'test-session',
      }

      const result = await sendChatMessage(request, {
        baseUrl: 'http://127.0.0.1:8000',
        mockMode: false,
      })

      expect(result.success).toBe(true)
      if (result.success) {
        expect(result.data.status).toBe('answered')
        expect(result.data.request_id).toBe('req-test-1234')
        expect(result.data.sources).toHaveLength(1)
        expect(result.data.sources[0].url).toBe('https://eurekasolutions.in/Eureka2026/services/netsuite/')
      }

      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/api/v1/chat',
        expect.objectContaining({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
          },
          body: JSON.stringify({
            message: 'What ERP software do you provide?',
            session_id: 'test-session',
            language: 'auto',
          }),
        })
      )
    })

    it('handles insufficient_evidence status', async () => {
      const mockResponseData = {
        request_id: 'req-insuff-01',
        answer: "I couldn't find enough information about that on the website.",
        status: 'insufficient_evidence',
        sources: [],
        message: null,
      }

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'x-request-id': 'req-insuff-01' }),
        json: async () => mockResponseData,
      })

      const result = await sendChatMessage(
        { message: 'What was your revenue in 1992?' },
        { baseUrl: 'http://127.0.0.1:8000', mockMode: false }
      )

      expect(result.success).toBe(true)
      if (result.success) {
        expect(result.data.status).toBe('insufficient_evidence')
        expect(result.data.sources).toEqual([])
      }
    })

    it('handles out_of_scope status', async () => {
      const mockResponseData = {
        request_id: 'req-scope-01',
        answer: 'I am dedicated to Eureka Solutions software services.',
        status: 'out_of_scope',
        sources: [],
        message: null,
      }

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'x-request-id': 'req-scope-01' }),
        json: async () => mockResponseData,
      })

      const result = await sendChatMessage(
        { message: 'How do I bake bread?' },
        { baseUrl: 'http://127.0.0.1:8000', mockMode: false }
      )

      expect(result.success).toBe(true)
      if (result.success) {
        expect(result.data.status).toBe('out_of_scope')
      }
    })

    it('handles HTTP 429 rate limit with retry-after header', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 429,
        headers: new Headers({
          'retry-after': '45',
          'x-request-id': 'req-rate-limit',
        }),
        json: async () => ({
          request_id: 'req-rate-limit',
          error: { code: 'rate_limit_exceeded', message: 'Rate limit exceeded' },
        }),
      })

      const result = await sendChatMessage(
        { message: 'Rapid query' },
        { baseUrl: 'http://127.0.0.1:8000', mockMode: false }
      )

      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.errorType).toBe('rate_limit')
        expect(result.retryAfterSeconds).toBe(45)
        expect(result.requestId).toBe('req-rate-limit')
      }
    })

    it('handles HTTP 503 service unavailable', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        headers: new Headers({ 'x-request-id': 'req-503-down' }),
        json: async () => ({
          request_id: 'req-503-down',
          error: { code: 'service_unavailable', message: 'Retrieval backend is down' },
        }),
      })

      const result = await sendChatMessage(
        { message: 'Hello' },
        { baseUrl: 'http://127.0.0.1:8000', mockMode: false }
      )

      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.errorType).toBe('unavailable')
        expect(result.message).toContain('Retrieval backend is down')
      }
    })

    it('handles HTTP 422 validation errors from FastAPI', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        headers: new Headers({ 'x-request-id': 'req-val-error' }),
        json: async () => ({
          detail: [{ loc: ['body', 'message'], msg: 'Field required' }],
        }),
      })

      const result = await sendChatMessage(
        { message: 'Valid query on client, rejected on server' },
        { baseUrl: 'http://127.0.0.1:8000', mockMode: false }
      )

      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.errorType).toBe('validation')
        expect(result.message).toContain('Field required')
      }
    })

    it('handles network failure', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))

      const result = await sendChatMessage(
        { message: 'Query with connection down' },
        { baseUrl: 'http://127.0.0.1:8000', mockMode: false }
      )

      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.errorType).toBe('network')
        expect(result.message).toContain('connection error')
      }
    })

    it('handles malformed JSON response', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => {
          throw new SyntaxError('Unexpected token < in JSON at position 0')
        },
      })

      const result = await sendChatMessage(
        { message: 'Query expecting JSON' },
        { baseUrl: 'http://127.0.0.1:8000', mockMode: false }
      )

      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.errorType).toBe('schema')
      }
    })

    it('handles mock mode when explicitly requested', async () => {
      const result = await sendChatMessage(
        { message: 'What is NetSuite?' },
        { mockMode: true }
      )

      expect(result.success).toBe(true)
      if (result.success) {
        expect(result.data.status).toBe('answered')
        expect(result.data.sources.length).toBeGreaterThan(0)
      }
    })
  })

  describe('getApiBaseUrl', () => {
    it('returns a sanitized base URL without trailing slash', () => {
      const url = getApiBaseUrl()
      expect(url.endsWith('/')).toBe(false)
      expect(url).toBeTruthy()
    })
  })
})
