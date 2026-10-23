import React from 'react'

export const ScopeBanner: React.FC = () => {
  return (
    <div className="eureka-scope-banner" role="note" aria-label="Scope notice">
      <svg
        className="eureka-scope-icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="16" x2="12" y2="12" />
        <line x1="12" y1="8" x2="12.01" y2="8" />
      </svg>
      <span>
        Answers are grounded in available Eureka Solutions website information. Inquiries outside our software engineering and solutions scope may be redirected.
      </span>
    </div>
  )
}
