import React from 'react'

export const LoadingIndicator: React.FC = () => {
  return (
    <div
      className="eureka-loading-indicator"
      role="status"
      aria-live="polite"
      aria-label="Ask Eureka AI is generating an answer"
    >
      <div className="eureka-loading-dot" aria-hidden="true" />
      <div className="eureka-loading-dot" aria-hidden="true" />
      <div className="eureka-loading-dot" aria-hidden="true" />
      <span className="eureka-sr-only">Ask Eureka AI is generating an answer...</span>
    </div>
  )
}
