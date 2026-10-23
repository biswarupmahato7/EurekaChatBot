/**
 * Citation Artifact Stripper & URL Sanitizer for Eureka Chatbot
 * Cleans inline citation markers and trailing reference blocks while preserving
 * valid markdown links, numbered lists, and meaningful bracketed text.
 */

/**
 * Remove inline citation markers (e.g. [Source 1], [1], [Source: ...]) and trailing
 * Sources/References sections while preserving meaningful bracketed text, numbers, and links.
 */
export function stripCitationArtifacts(text: string): string {
  if (!text) return ''

  let cleaned = text

  // 1. Remove trailing References / Sources section
  // Matches: \n\n### Sources\n... or \n\n**Sources:**\n... or \n\nSources:\n1. ...
  const trailingSourcesSectionRegex =
    /(?:\r?\n)+(?:#{1,6}\s*|\*{1,2})?(?:Sources|References|Citations)(?:\*{1,2}|:)*\s*(?:\r?\n+[\s\S]*)$/i

  cleaned = cleaned.replace(trailingSourcesSectionRegex, (match) => {
    // Only strip if the block actually contains citation patterns (urls, source items, bullet list)
    if (/https?:\/\/|\[Source|\burl\b|www\.|\d+\.\s+|-\s+/i.test(match)) {
      return ''
    }
    return match
  })

  // 2. Remove inline source markers like [Source 1], [Source 1, 2], [Source 1; Source 2], [Source: ...]
  cleaned = cleaned.replace(
    /\s*\[(?:Sources?|Ref|Reference)(?::\s*[^\]\n]+|\s*\d+(?:[\s,;–-]+(?:and\s*)?(?:Sources?\s*)?\d+)*)\](?!\()/gi,
    ''
  )

  // 3. Remove inline numeric citation markers like [1], [2], [1, 2], [1-3]
  // Must NOT be preceded by a word character (preserves array[0], item[1])
  // Must NOT be a 4-digit year (preserves [2024-2026])
  // Must NOT be immediately followed by ( (preserves markdown link [1](url))
  cleaned = cleaned.replace(
    /(?<![\w$])\s*\[\s*\d{1,2}(?:\s*[,;–-]\s*\d{1,2})*\s*\](?!\()/g,
    ''
  )

  // 4. Clean up any leftover awkward whitespace before punctuation, duplicate periods, and collapse extra spaces
  cleaned = cleaned
    .replace(/\s+([.,;:!?])/g, '$1')
    .replace(/\.{2,}/g, '.')
    .replace(/(?<=\S)[^\S\r\n]{2,}/g, ' ')
    .trim()

  return cleaned
}

/**
 * Validates and sanitizes link targets.
 * Blocks dangerous protocols (javascript:, data:, vbscript:, file:).
 */
export function safeUrlTransform(url: string): string {
  if (!url) return ''
  const trimmed = url.trim()
  const lower = trimmed.toLowerCase()
  if (
    lower.startsWith('javascript:') ||
    lower.startsWith('data:') ||
    lower.startsWith('vbscript:') ||
    lower.startsWith('file:')
  ) {
    return ''
  }
  return trimmed
}
