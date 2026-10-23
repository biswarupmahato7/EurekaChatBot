import React, { useState, useRef, useCallback } from 'react'
import type { ChatMessage, ChatRequest } from '../api/types'
import { sendChatMessage } from '../api/chatClient'
import { ChatLauncher } from './ChatLauncher'
import { ChatPanel } from './ChatPanel'
import '../styles/eureka-tokens.css'
import '../styles/eureka-widget.css'

export interface AskEurekaWidgetProps {
  initialOpen?: boolean
  apiUrl?: string
  mockMode?: boolean
}

function generateSessionId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `sess-${crypto.randomUUID()}`
  }
  return `sess-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

export const AskEurekaWidget: React.FC<AskEurekaWidgetProps> = ({
  initialOpen = false,
  apiUrl,
  mockMode,
}) => {
  const [isOpen, setIsOpen] = useState(initialOpen)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [sessionId, setSessionId] = useState(generateSessionId)
  const [draftText, setDraftText] = useState('')
  const [isDuplicate] = useState(() => {
    if (typeof window !== 'undefined') {
      const win = window as unknown as Record<string, boolean>
      if (win.__EUREKA_WIDGET_ACTIVE__) {
        console.warn('Duplicate AskEurekaWidget detected; mounting suppressed.')
        return true
      }
      win.__EUREKA_WIDGET_ACTIVE__ = true
    }
    return false
  })

  const launcherRef = useRef<HTMLButtonElement>(null)
  const activeAbortControllerRef = useRef<AbortController | null>(null)
  const requestVersionRef = useRef(0)
  const messagesRef = useRef<ChatMessage[]>(messages)

  React.useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  // UI-020: Clean up singleton marker on unmount
  React.useEffect(() => {
    return () => {
      if (typeof window !== 'undefined') {
        const win = window as unknown as Record<string, boolean>
        win.__EUREKA_WIDGET_ACTIVE__ = false
      }
    }
  }, [])

  // Toggle open/close with focus restoration
  const handleToggle = useCallback(() => {
    setIsOpen((prev) => {
      const next = !prev
      if (!next) {
        // Restoring focus to launcher button upon close
        setTimeout(() => {
          launcherRef.current?.focus()
        }, 50)
      }
      return next
    })
  }, [])

  const handleClose = useCallback(() => {
    setIsOpen(false)
    setTimeout(() => {
      launcherRef.current?.focus()
    }, 50)
  }, [])

  // Reset conversation safely, cancelling stale in-flight requests
  const handleReset = useCallback(() => {
    if (activeAbortControllerRef.current) {
      activeAbortControllerRef.current.abort()
      activeAbortControllerRef.current = null
    }
    requestVersionRef.current += 1
    setMessages([])
    setIsLoading(false)
    setDraftText('')
    setSessionId(generateSessionId())
  }, [])

  // Send message handler
  const handleSend = useCallback(
    async (text: string) => {
      if (!text || !text.trim() || isLoading) {
        return
      }

      const trimmedText = text.trim()
      const userMsgId = `user-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
      const userMessage: ChatMessage = {
        id: userMsgId,
        sender: 'user',
        text: trimmedText,
        timestamp: Date.now(),
      }

      // Append user message immediately
      setMessages((prev) => [...prev, userMessage])
      setIsLoading(true)
      setDraftText('')

      // Prepare request correlation & cancellation
      const currentVersion = ++requestVersionRef.current
      const abortController = new AbortController()
      activeAbortControllerRef.current = abortController

      const conversationHistory = messagesRef.current.slice(-6).map((m) => ({
        role: m.sender,
        content: m.text,
      }))

      const requestPayload: ChatRequest = {
        message: trimmedText,
        session_id: sessionId,
        language: 'auto',
        conversation_history: conversationHistory,
      }


      try {
        const result = await sendChatMessage(requestPayload, {
          baseUrl: apiUrl,
          mockMode: mockMode,
          signal: abortController.signal,
        })

        // Check if this response belongs to the current conversation version
        if (requestVersionRef.current !== currentVersion) {
          // Stale request discarded
          return
        }

        if (result.success) {
          const assistantMsgId = `asst-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
          const assistantMessage: ChatMessage = {
            id: assistantMsgId,
            sender: 'assistant',
            text: result.data.answer,
            timestamp: Date.now(),
            status: result.data.status,
            sources: result.data.sources,
            quickReplies: result.data.quick_replies,
            requestId: result.data.request_id,
            isError: false,
          }
          setMessages((prev) => [...prev, assistantMessage])
        } else {
          // Failure: preserve draft text and show error banner with retry option
          setDraftText(trimmedText)
          const errorMsgId = `err-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
          const errorMessage: ChatMessage = {
            id: errorMsgId,
            sender: 'assistant',
            text: result.message,
            timestamp: Date.now(),
            requestId: result.requestId,
            isError: true,
            errorType: result.errorType,
            canRetry: true,
            failedUserMessage: trimmedText,
          }
          setMessages((prev) => [...prev, errorMessage])
        }
      } catch {
        if (requestVersionRef.current === currentVersion) {
          setDraftText(trimmedText)
          const errorMsgId = `err-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
          const errorMessage: ChatMessage = {
            id: errorMsgId,
            sender: 'assistant',
            text: 'An unexpected connection error occurred. Please try again.',
            timestamp: Date.now(),
            isError: true,
            canRetry: true,
            failedUserMessage: trimmedText,
          }
          setMessages((prev) => [...prev, errorMessage])
        }
      } finally {
        if (requestVersionRef.current === currentVersion) {
          setIsLoading(false)
          activeAbortControllerRef.current = null
        }
      }
    },
    [apiUrl, mockMode, isLoading, sessionId]
  )

  const handleSelectStarter = useCallback(
    (question: string) => {
      handleSend(question)
    },
    [handleSend]
  )

  const handleRetry = useCallback(
    (failedText: string) => {
      handleSend(failedText)
    },
    [handleSend]
  )

  const handleSelectQuickReply = useCallback(
    (option: string) => {
      handleSend(option)
    },
    [handleSend]
  )

  if (isDuplicate) {
    return null
  }

  return (
    <div className="eureka-widget-root">
      <ChatLauncher
        isOpen={isOpen}
        onClick={handleToggle}
        launcherRef={launcherRef}
      />

      <ChatPanel
        isOpen={isOpen}
        onClose={handleClose}
        onReset={handleReset}
        messages={messages}
        isLoading={isLoading}
        onSend={handleSend}
        onSelectStarter={handleSelectStarter}
        onSelectQuickReply={handleSelectQuickReply}
        onRetry={handleRetry}
        draftText={draftText}
      />
    </div>
  )
}
