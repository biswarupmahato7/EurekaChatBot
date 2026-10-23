import { describe, it, expect } from 'vitest'
import { isValidCitationUrl, filterSafeSources } from '../api/urlValidator'

describe('urlValidator', () => {
  it('approves legitimate https eureka website urls', () => {
    expect(isValidCitationUrl('https://eurekasolutions.in/Eureka2026/')).toBe(true)
    expect(isValidCitationUrl('https://eurekasolutions.in/Eureka2026/services/netsuite/')).toBe(true)
    expect(isValidCitationUrl('https://www.eurekasolutions.in/about')).toBe(true)
  })

  it('rejects unsafe schemes', () => {
    expect(isValidCitationUrl('javascript:alert("XSS")')).toBe(false)
    expect(isValidCitationUrl('data:text/html,<script>alert(1)</script>')).toBe(false)
    expect(isValidCitationUrl('vbscript:msgbox("test")')).toBe(false)
    expect(isValidCitationUrl('file:///etc/passwd')).toBe(false)
  })

  it('rejects non-https URLs', () => {
    expect(isValidCitationUrl('http://eurekasolutions.in/test')).toBe(false)
  })

  it('rejects unauthorized external domains', () => {
    expect(isValidCitationUrl('https://malicious-phishing-site.com/')).toBe(false)
    expect(isValidCitationUrl('https://google.com')).toBe(false)
    expect(isValidCitationUrl('https://eurekasolutions.in.attacker.com/')).toBe(false)
  })

  it('rejects empty or malformed strings', () => {
    expect(isValidCitationUrl('')).toBe(false)
    expect(isValidCitationUrl('   ')).toBe(false)
    expect(isValidCitationUrl(null as unknown as string)).toBe(false)
    expect(isValidCitationUrl('not-a-valid-url')).toBe(false)
  })

  it('filterSafeSources filters out untrusted citations while preserving valid ones', () => {
    const rawSources = [
      {
        title: 'Valid Oracle NetSuite Service',
        url: 'https://eurekasolutions.in/Eureka2026/services/netsuite/',
        snippet: 'NetSuite implementation experts.',
      },
      {
        title: 'Malicious External Site',
        url: 'https://attacker.com/steal-creds',
        snippet: 'Click here.',
      },
      {
        title: 'Script Injection Link',
        url: 'javascript:alert(1)',
        snippet: 'Exploit attempt.',
      },
      {
        title: 'Cloud Integration',
        url: 'https://eurekasolutions.in/Eureka2026/services/cloud-integration/',
        snippet: 'Seamless cloud sync.',
      },
    ]

    const safe = filterSafeSources(rawSources)
    expect(safe).toHaveLength(2)
    expect(safe[0].title).toBe('Valid Oracle NetSuite Service')
    expect(safe[1].title).toBe('Cloud Integration')
  })

  it('filterSafeSources returns empty array for null/undefined/empty input', () => {
    expect(filterSafeSources(null)).toEqual([])
    expect(filterSafeSources(undefined)).toEqual([])
    expect(filterSafeSources([])).toEqual([])
  })
})
