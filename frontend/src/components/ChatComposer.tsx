import React, { useRef, useState } from 'react'

interface ChatComposerProps {
  onSend: (message: string) => void
  isLoading: boolean
  initialText?: string
  textareaRef?: React.Ref<HTMLTextAreaElement>
}

const MAX_CHARS = 2000

export const ChatComposer: React.FC<ChatComposerProps> = ({
  onSend,
  isLoading,
  initialText = '',
  textareaRef,
}) => {
  const [text, setText] = useState(initialText)
  const isSubmittingRef = useRef(false)

  const trimmed = text.trim()
  const charCount = text.length
  const isTooLong = charCount > MAX_CHARS
  const isValid = trimmed.length > 0 && !isTooLong && !isLoading

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) {
      e.preventDefault()
    }

    if (!isValid || isSubmittingRef.current) {
      return
    }

    isSubmittingRef.current = true
    const messageToSend = trimmed
    setText('')

    try {
      onSend(messageToSend)
    } finally {
      setTimeout(() => {
        isSubmittingRef.current = false
      }, 100)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <form className="eureka-composer-wrapper" onSubmit={handleSubmit} role="form" aria-label="Message composer">
      <div className="eureka-composer-input-row">
        <textarea
          ref={textareaRef}
          className="eureka-composer-textarea"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about Eureka Solutions..."
          aria-label="Your question"
          rows={1}
          maxLength={MAX_CHARS + 50}
          disabled={isLoading}
        />

        <button
          type="submit"
          className="eureka-send-btn"
          disabled={!isValid}
          title={isLoading ? 'Assistant is answering...' : 'Send message (Enter)'}
          aria-label="Send message"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>

      <div className="eureka-composer-footer">
        <span>Enter to send, Shift+Enter for new line</span>
        <span
          className={`eureka-char-counter ${
            isTooLong || charCount > 1900 ? 'eureka-char-limit-warning' : ''
          }`}
          aria-live="polite"
        >
          {charCount} / {MAX_CHARS}
        </span>
      </div>
    </form>
  )
}
