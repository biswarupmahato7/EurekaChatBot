import React from 'react'

interface ChatHeaderProps {
  onClose: () => void
  onReset: () => void
  hasMessages: boolean
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({
  onClose,
  onReset,
  hasMessages,
}) => {
  return (
    <header className="eureka-chat-header">
      <div className="eureka-header-info">
        <h2 id="eureka-dialog-title" className="eureka-header-title">
          <span>Ask Eureka AI</span>
          <span className="eureka-header-badge" aria-label="Artificial Intelligence">
            AI
          </span>
        </h2>
        <p className="eureka-header-subtitle">
          Answers based on Eureka Solutions website information
        </p>
      </div>

      <div className="eureka-header-actions">
        {hasMessages && (
          <button
            type="button"
            className="eureka-btn-icon"
            onClick={onReset}
            title="Start new conversation"
            aria-label="Start new conversation"
          >
            <svg
              width="17"
              height="17"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
            </svg>
          </button>
        )}

        <button
          type="button"
          className="eureka-btn-icon"
          onClick={onClose}
          title="Close chat"
          aria-label="Close chat"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
    </header>
  )
}
