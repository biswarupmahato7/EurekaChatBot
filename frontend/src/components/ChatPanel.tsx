import React, { useEffect, useRef } from 'react'
import type { ChatMessage } from '../api/types'
import { ChatHeader } from './ChatHeader'
import { ScopeBanner } from './ScopeBanner'
import { MessageList } from './MessageList'
import { ChatComposer } from './ChatComposer'

interface ChatPanelProps {
  isOpen: boolean
  onClose: () => void
  onReset: () => void
  messages: ChatMessage[]
  isLoading: boolean
  onSend: (message: string) => void
  onSelectStarter: (question: string) => void
  onRetry: (text: string) => void
  onSelectQuickReply?: (option: string) => void
  draftText?: string
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  isOpen,
  onClose,
  onReset,
  messages,
  isLoading,
  onSend,
  onSelectStarter,
  onRetry,
  onSelectQuickReply,
  draftText,
}) => {
  const panelRef = useRef<HTMLDivElement>(null)
  const composerTextareaRef = useRef<HTMLTextAreaElement | null>(null)

  // Manage Escape key to close & Focus trap
  useEffect(() => {
    if (!isOpen) return

    // Focus composer upon opening
    setTimeout(() => {
      composerTextareaRef.current?.focus()
    }, 50)

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
        return
      }

      // Focus trap logic
      if (e.key === 'Tab' && panelRef.current) {
        const focusableElements = panelRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), textarea:not([disabled]), input:not([disabled]), a[href]:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )

        if (focusableElements.length === 0) return

        const firstElement = focusableElements[0]
        const lastElement = focusableElements[focusableElements.length - 1]

        if (e.shiftKey) {
          if (document.activeElement === firstElement) {
            e.preventDefault()
            lastElement.focus()
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault()
            firstElement.focus()
          }
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div
      ref={panelRef}
      id="eureka-chat-dialog"
      className="eureka-chat-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="eureka-dialog-title"
    >
      <ChatHeader
        onClose={onClose}
        onReset={onReset}
        hasMessages={messages.length > 0}
      />

      <ScopeBanner />

      <MessageList
        messages={messages}
        isLoading={isLoading}
        onSelectStarter={onSelectStarter}
        onRetry={onRetry}
        onSelectQuickReply={onSelectQuickReply}
      />

      <ChatComposer
        key={draftText || 'composer'}
        onSend={onSend}
        isLoading={isLoading}
        initialText={draftText}
        textareaRef={composerTextareaRef}
      />
    </div>
  )
}
