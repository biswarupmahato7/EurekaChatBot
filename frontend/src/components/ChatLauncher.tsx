import React from 'react'

interface ChatLauncherProps {
  isOpen: boolean
  onClick: () => void
  launcherRef?: React.Ref<HTMLButtonElement>
}

export const ChatLauncher: React.FC<ChatLauncherProps> = ({
  isOpen,
  onClick,
  launcherRef,
}) => {
  return (
    <button
      ref={launcherRef}
      type="button"
      className="eureka-launcher"
      onClick={onClick}
      aria-expanded={isOpen}
      aria-controls="eureka-chat-dialog"
      aria-label={isOpen ? 'Close Ask Eureka AI chat' : 'Open Ask Eureka AI chat'}
      title="Ask Eureka AI"
    >
      <svg
        className="eureka-launcher-icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        <path d="M8 10h.01" />
        <path d="M12 10h.01" />
        <path d="M16 10h.01" />
      </svg>
      <span className="eureka-launcher-label">Ask Eureka AI</span>
    </button>
  )
}
