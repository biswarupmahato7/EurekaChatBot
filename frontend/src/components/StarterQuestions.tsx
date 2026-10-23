import React from 'react'
import { VERIFIED_STARTER_QUESTIONS } from '../constants/starterQuestions'

interface StarterQuestionsProps {
  onSelect: (question: string) => void
  disabled?: boolean
}

export const StarterQuestions: React.FC<StarterQuestionsProps> = ({
  onSelect,
  disabled = false,
}) => {
  return (
    <div className="eureka-starter-container" aria-label="Suggested starter questions">
      <div className="eureka-starter-prompt">Suggested Questions:</div>
      {VERIFIED_STARTER_QUESTIONS.map((question, idx) => (
        <button
          key={idx}
          type="button"
          className="eureka-starter-btn"
          onClick={() => onSelect(question)}
          disabled={disabled}
        >
          <span>{question}</span>
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
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>
      ))}
    </div>
  )
}
