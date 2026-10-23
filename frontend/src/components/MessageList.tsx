import React, { useEffect, useRef } from 'react'
import type { ChatMessage } from '../api/types'
import { MessageItem } from './MessageItem'
import { StarterQuestions } from './StarterQuestions'
import { LoadingIndicator } from './LoadingIndicator'

interface MessageListProps {
  messages: ChatMessage[]
  isLoading: boolean
  onSelectStarter: (question: string) => void
  onRetry: (text: string) => void
  onSelectQuickReply?: (option: string) => void
}

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  isLoading,
  onSelectStarter,
  onRetry,
  onSelectQuickReply,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const lastAssistantId = [...messages].reverse().find((m) => m.sender === 'assistant')?.id

  return (
    <div
      className="eureka-message-list"
      role="log"
      aria-live="polite"
      aria-label="Conversation history"
    >
      {messages.length === 0 ? (
        <div style={{ padding: '8px 4px' }}>
          <div style={{ fontSize: '0.9rem', color: '#495057', marginBottom: '14px', lineHeight: '1.4' }}>
            Hello! Ask me anything about Eureka Solutions services, ERP implementations, and digital transformation.
          </div>
          <StarterQuestions onSelect={onSelectStarter} disabled={isLoading} />
        </div>
      ) : (
        messages.map((msg) => (
          <MessageItem
            key={msg.id}
            message={msg}
            onRetry={onRetry}
            onSelectQuickReply={onSelectQuickReply}
            isLatestAssistant={msg.id === lastAssistantId}
            isLoading={isLoading}
          />
        ))
      )}

      {isLoading && <LoadingIndicator />}

      <div ref={bottomRef} aria-hidden="true" />
    </div>
  )
}
