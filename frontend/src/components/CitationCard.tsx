import React from 'react'
import type { SourceItem } from '../api/types'
import { isValidCitationUrl } from '../api/urlValidator'

interface CitationCardProps {
  source: SourceItem
  index: number
}

export const CitationCard: React.FC<CitationCardProps> = ({ source, index }) => {
  const isSafe = isValidCitationUrl(source.url)

  if (!isSafe) {
    // Render without clickable link to prevent XSS or navigation to untrusted destinations
    return (
      <div className="eureka-citation-card" data-testid={`citation-${index}`}>
        <div className="eureka-citation-title">
          <span>{source.title}</span>
        </div>
        {source.snippet && (
          <div className="eureka-citation-snippet">{source.snippet}</div>
        )}
      </div>
    )
  }

  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className="eureka-citation-card"
      aria-label={`Source ${index + 1}: ${source.title} (opens in a new tab)`}
      data-testid={`citation-${index}`}
    >
      <div className="eureka-citation-title">
        <span>{source.title}</span>
        <svg
          className="eureka-citation-icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
          <polyline points="15 3 21 3 21 9" />
          <line x1="10" y1="14" x2="21" y2="3" />
        </svg>
      </div>
      {source.snippet && (
        <div className="eureka-citation-snippet">{source.snippet}</div>
      )}
    </a>
  )
}
