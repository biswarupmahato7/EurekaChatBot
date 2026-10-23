import React from 'react'

interface StatusNoticeProps {
  type: 'warning' | 'danger' | 'info'
  message: string
  requestId?: string
  retryAfterSeconds?: number
  onRetry?: () => void
}

export const StatusNotice: React.FC<StatusNoticeProps> = ({
  type,
  message,
  requestId,
  retryAfterSeconds,
  onRetry,
}) => {
  const typeClass =
    type === 'danger'
      ? 'eureka-status-notice-danger'
      : type === 'warning'
      ? 'eureka-status-notice-warning'
      : 'eureka-status-notice-info'

  return (
    <div className={`eureka-status-notice ${typeClass}`} role="alert">
      <div>{message}</div>

      {retryAfterSeconds && (
        <div style={{ fontSize: '0.8rem', opacity: 0.85 }}>
          Estimated retry time: {retryAfterSeconds} seconds.
        </div>
      )}

      {requestId && (
        <div style={{ fontSize: '0.75rem', opacity: 0.75 }}>
          Reference ID: {requestId}
        </div>
      )}

      {onRetry && (
        <button
          type="button"
          className="eureka-retry-btn"
          onClick={onRetry}
          aria-label="Retry question"
        >
          Try Again
        </button>
      )}
    </div>
  )
}
