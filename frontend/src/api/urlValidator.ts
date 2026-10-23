/**
 * URL and Citation Validation
 * Enforces origin and scheme security policies to avoid XSS, phishing, or unsafe navigation.
 */
import type { SourceItem } from './types'

// Allowed hostname for citations based on project specification
const ALLOWED_HOSTNAMES = new Set([
  'eurekasolutions.in',
  'www.eurekasolutions.in',
])

/**
 * Validates a citation URL against scheme and hostname policies.
 * Only HTTPS URLs under the approved domain are allowed.
 */
export function isValidCitationUrl(urlString: string | null | undefined): boolean {
  if (!urlString || typeof urlString !== 'string') {
    return false
  }

  const trimmed = urlString.trim()
  if (!trimmed) {
    return false
  }

  // Reject dangerous schemes explicitly before URL parsing
  const lower = trimmed.toLowerCase()
  if (
    lower.startsWith('javascript:') ||
    lower.startsWith('data:') ||
    lower.startsWith('vbscript:') ||
    lower.startsWith('file:')
  ) {
    return false
  }

  try {
    const parsed = new URL(trimmed)

    // Strictly enforce https scheme
    if (parsed.protocol !== 'https:') {
      return false
    }

    // Enforce approved hostnames
    const hostname = parsed.hostname.toLowerCase()
    if (!ALLOWED_HOSTNAMES.has(hostname) && !hostname.endsWith('.eurekasolutions.in')) {
      return false
    }

    return true
  } catch {
    return false
  }
}

/**
 * Sanitizes and filters source citations, keeping only items with safe URLs,
 * valid titles, and valid snippets.
 */
export function filterSafeSources(sources: unknown): SourceItem[] {
  if (!Array.isArray(sources)) {
    return []
  }

  const safeList: SourceItem[] = []

  for (const item of sources) {
    if (!item || typeof item !== 'object') {
      continue
    }

    const { title, url, snippet } = item as Record<string, unknown>

    if (
      typeof title === 'string' &&
      typeof url === 'string' &&
      typeof snippet === 'string' &&
      isValidCitationUrl(url)
    ) {
      safeList.push({
        title: title.trim(),
        url: url.trim(),
        snippet: snippet.trim(),
      })
    }
  }

  return safeList
}
