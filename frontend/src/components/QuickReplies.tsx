import React from 'react'

export interface QuickRepliesProps {
  options: string[]
  onSelect: (option: string) => void
  disabled?: boolean
}

export const QuickReplies: React.FC<QuickRepliesProps> = ({
  options,
  onSelect,
  disabled = false,
}) => {
  if (!options || options.length === 0) {
    return null
  }

  return (
    <div
      className="eureka-quick-replies"
      role="group"
      aria-label="Quick reply options"
      data-testid="quick-replies-group"
    >
      {options.map((option, index) => (
        <button
          key={`${index}-${option}`}
          type="button"
          className="eureka-quick-reply-chip"
          data-testid="quick-reply-chip"
          disabled={disabled}
          onClick={() => {
            if (!disabled) {
              onSelect(option)
            }
          }}
          onKeyDown={(e) => {
            if (disabled) return
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              onSelect(option)
            }
          }}
          aria-label={option}
        >
          {option}
        </button>
      ))}
    </div>
  )
}
