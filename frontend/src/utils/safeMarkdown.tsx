/**
 * Safe Markdown to React Element Parser
 * Renders structured markdown (paragraphs, lists, headings, bold, italic, code, tables)
 * with robust sanitization, custom semantic components, and safe URL enforcement.
 *
 * Prevents XSS and script injection without dangerouslySetInnerHTML.
 * Strips inline citation artifacts ([Source 1], [1], [Source: ...]) and references sections.
 */
import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { stripCitationArtifacts, safeUrlTransform } from './citationCleaner'

export interface SafeMarkdownProps {
  content: string
  className?: string
}

export const SafeMarkdown: React.FC<SafeMarkdownProps> = ({ content, className = '' }) => {
  if (!content) return null

  // Pre-process text to remove inline citation markers and trailing source lists
  const cleanedContent = stripCitationArtifacts(content)
  if (!cleanedContent) return null

  return (
    <div className={`eureka-markdown-body ${className}`.trim()}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        urlTransform={safeUrlTransform}
        components={{
          p({ children }) {
            return <p className="eureka-markdown-paragraph">{children}</p>
          },
          h1({ children }) {
            return <h3 className="eureka-markdown-heading eureka-markdown-h1">{children}</h3>
          },
          h2({ children }) {
            return <h3 className="eureka-markdown-heading eureka-markdown-h2">{children}</h3>
          },
          h3({ children }) {
            return <h4 className="eureka-markdown-heading eureka-markdown-h3">{children}</h4>
          },
          h4({ children }) {
            return <h5 className="eureka-markdown-heading eureka-markdown-h4">{children}</h5>
          },
          h5({ children }) {
            return <h6 className="eureka-markdown-heading eureka-markdown-h5">{children}</h6>
          },
          h6({ children }) {
            return <h6 className="eureka-markdown-heading eureka-markdown-h6">{children}</h6>
          },
          ul({ children }) {
            return <ul className="eureka-markdown-list">{children}</ul>
          },
          ol({ children }) {
            return <ol className="eureka-markdown-ordered-list">{children}</ol>
          },
          li({ children }) {
            return <li className="eureka-markdown-list-item">{children}</li>
          },
          strong({ children }) {
            return <strong className="eureka-markdown-strong">{children}</strong>
          },
          em({ children }) {
            return <em className="eureka-markdown-em">{children}</em>
          },
          blockquote({ children }) {
            return <blockquote className="eureka-markdown-blockquote">{children}</blockquote>
          },
          pre({ children }) {
            return <pre className="eureka-code-block">{children}</pre>
          },
          code({ className, children, ...props }) {
            const isBlock = className && className.includes('language-')
            if (isBlock) {
              return (
                <code className={`eureka-code-content ${className}`} {...props}>
                  {children}
                </code>
              )
            }
            return (
              <code className="eureka-inline-code" {...props}>
                {children}
              </code>
            )
          },
          table({ children }) {
            return (
              <div className="eureka-table-wrapper">
                <table className="eureka-markdown-table">{children}</table>
              </div>
            )
          },
          th({ children }) {
            return <th className="eureka-table-header">{children}</th>
          },
          td({ children }) {
            return <td className="eureka-table-cell">{children}</td>
          },
          a({ href, children }) {
            const safeHref = safeUrlTransform(href || '')
            if (!safeHref) {
              return <span className="eureka-markdown-neutralized-link">{children}</span>
            }
            const isExternal =
              safeHref.startsWith('http://') ||
              safeHref.startsWith('https://') ||
              safeHref.startsWith('//')
            return (
              <a
                href={safeHref}
                className="eureka-markdown-link"
                target={isExternal ? '_blank' : undefined}
                rel={isExternal ? 'noopener noreferrer' : undefined}
              >
                {children}
              </a>
            )
          },
        }}
      >
        {cleanedContent}
      </ReactMarkdown>
    </div>
  )
}
