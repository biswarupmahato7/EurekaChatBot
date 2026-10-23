import React from 'react'
import type { ChatMessage } from '../api/types'
import { SafeMarkdown } from '../utils/safeMarkdown'
import { StatusNotice } from './StatusNotice'
import { QuickReplies } from './QuickReplies'

interface MessageItemProps {
  message: ChatMessage
  onRetry?: (text: string) => void
  onSelectQuickReply?: (option: string) => void
  isLatestAssistant?: boolean
  isLoading?: boolean
}

export const MessageItem: React.FC<MessageItemProps> = ({
  message,
  onRetry,
  onSelectQuickReply,
  isLatestAssistant = true,
  isLoading = false,
}) => {
  if (message.sender === 'user') {
    return (
      <div className="eureka-message-user">
        <div className="eureka-bubble-user" data-testid="user-message">
          {message.text}
        </div>
      </div>
    )
  }

  // Assistant Message
  return (
    <div className="eureka-message-assistant" data-testid="assistant-message">
      {message.isError ? (
        <StatusNotice
          type="danger"
          message={message.text}
          requestId={message.requestId}
          onRetry={
            message.canRetry && message.failedUserMessage && onRetry
              ? () => onRetry(message.failedUserMessage!)
              : undefined
          }
        />
      ) : (
        <div className="eureka-bubble-assistant">
          <SafeMarkdown content={message.text} />

          {/* Quick Reply Clarification Options */}
          {message.quickReplies && message.quickReplies.length > 0 && onSelectQuickReply && (
            <QuickReplies
              options={message.quickReplies}
              onSelect={onSelectQuickReply}
              disabled={!isLatestAssistant || isLoading}
            />
          )}

          {/* Contextual notice if insufficient evidence or out of scope */}
          {message.status === 'insufficient_evidence' && (
            <div
              className="eureka-assistant-context-notice"
              data-testid="insufficient-evidence-notice"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <span>Note: The website knowledge base did not contain specific details for this query.</span>
            </div>
          )}

          {message.status === 'out_of_scope' && (
            <div
              className="eureka-assistant-context-notice"
              data-testid="out-of-scope-notice"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <span>Note: This assistant is dedicated to Eureka Solutions services and solutions.</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
