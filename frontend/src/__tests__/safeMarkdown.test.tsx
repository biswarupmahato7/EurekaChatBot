import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SafeMarkdown } from '../utils/safeMarkdown'
import { stripCitationArtifacts, safeUrlTransform } from '../utils/citationCleaner'

describe('SafeMarkdown - Formatting & Rendering', () => {
  it('renders simple text paragraphs without raw HTML vulnerability', () => {
    const text = 'Eureka Solutions delivers award-winning ERP implementation.'
    const { container } = render(<SafeMarkdown content={text} />)

    expect(screen.getByText(text)).toBeInTheDocument()
    expect(container.querySelector('p')).toBeInTheDocument()
    expect(container.querySelector('p')).toHaveClass('eureka-markdown-paragraph')
  })

  it('escapes and neutralizes raw HTML or script tags safely without active DOM execution', () => {
    const malicious = '<script>window.pwned = true;</script><img src="x" onerror="alert(1)"/>'
    const { container } = render(<SafeMarkdown content={malicious} />)

    // The script and onerror tags must NOT be present as active elements in the DOM
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    // Rendered harmlessly as escaped text
    expect(screen.getByText(/<script>/)).toBeInTheDocument()
  })

  it('renders markdown headings with proper classes and semantic tags', () => {
    const markdown = `# Main Title\n## Secondary Heading\n### Third Level Heading\n#### Fourth Level Heading`
    const { container } = render(<SafeMarkdown content={markdown} />)

    const headings = container.querySelectorAll('.eureka-markdown-heading')
    expect(headings.length).toBeGreaterThanOrEqual(4)
    expect(screen.getByText('Main Title')).toBeInTheDocument()
    expect(screen.getByText('Secondary Heading')).toBeInTheDocument()
    expect(screen.getByText('Third Level Heading')).toBeInTheDocument()
    expect(screen.getByText('Fourth Level Heading')).toBeInTheDocument()
  })

  it('renders unordered and ordered lists with correct list items', () => {
    const markdown = `
- Oracle NetSuite ERP
- Cloud Data Integration
- Banking Solutions

1. Initial Assessment
2. Solution Design
3. Production Go-Live
`
    const { container } = render(<SafeMarkdown content={markdown} />)

    expect(container.querySelector('ul')).toHaveClass('eureka-markdown-list')
    expect(container.querySelector('ol')).toHaveClass('eureka-markdown-ordered-list')

    const listItems = container.querySelectorAll('li')
    expect(listItems.length).toBe(6)
    expect(screen.getByText('Oracle NetSuite ERP')).toBeInTheDocument()
    expect(screen.getByText('Initial Assessment')).toBeInTheDocument()
  })

  it('renders nested lists cleanly', () => {
    const markdown = `- ERP Systems\n    - NetSuite\n    - Sage\n- Cloud Engineering`
    const { container } = render(<SafeMarkdown content={markdown} />)
    const uls = container.querySelectorAll('ul')
    expect(uls.length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('NetSuite')).toBeInTheDocument()
  })

  it('renders bold, italic, inline code, and fenced code blocks', () => {
    const markdown = `We provide **NetSuite** with *high reliability* and \`REST\` APIs.\n\n\`\`\`json\n{\n  "service": "ERP"\n}\n\`\`\``
    const { container } = render(<SafeMarkdown content={markdown} />)

    const strong = container.querySelector('strong')
    expect(strong).not.toBeNull()
    expect(strong?.textContent).toBe('NetSuite')
    expect(strong).toHaveClass('eureka-markdown-strong')

    const em = container.querySelector('em')
    expect(em).not.toBeNull()
    expect(em?.textContent).toBe('high reliability')
    expect(em).toHaveClass('eureka-markdown-em')

    const inlineCode = container.querySelector('.eureka-inline-code')
    expect(inlineCode).not.toBeNull()
    expect(inlineCode?.textContent).toBe('REST')

    const codeBlock = container.querySelector('pre')
    expect(codeBlock).not.toBeNull()
    expect(codeBlock).toHaveClass('eureka-code-block')
    expect(codeBlock?.textContent).toContain('"service": "ERP"')
  })

  it('renders GitHub-flavored markdown tables with header and cell styling', () => {
    const tableMarkdown = `
| Service | Platform | Experience |
| :--- | :--- | :--- |
| ERP Implementation | NetSuite | 20+ Years |
| System Integration | Azure / AWS | 15+ Years |
`
    const { container } = render(<SafeMarkdown content={tableMarkdown} />)

    const tableWrapper = container.querySelector('.eureka-table-wrapper')
    expect(tableWrapper).toBeInTheDocument()

    const table = container.querySelector('table')
    expect(table).toHaveClass('eureka-markdown-table')

    const headers = container.querySelectorAll('th')
    expect(headers).toHaveLength(3)
    expect(headers[0].textContent).toBe('Service')

    const cells = container.querySelectorAll('td')
    expect(cells.length).toBe(6)
    expect(cells[0].textContent).toBe('ERP Implementation')
    expect(cells[1].textContent).toBe('NetSuite')
  })

  it('renders safe markdown links with rel and target attributes', () => {
    const markdown = 'Visit our [Official Website](https://eurekasolutions.in) for details.'
    const { container } = render(<SafeMarkdown content={markdown} />)

    const link = container.querySelector('a')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', 'https://eurekasolutions.in')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(link).toHaveClass('eureka-markdown-link')
  })

  it('blocks and neutralizes dangerous URL schemes in markdown links', () => {
    const maliciousLinks = `
[Exploit JS](javascript:alert('pwned'))
[Exploit Data](data:text/html,<script>alert(1)</script>)
[Exploit VBS](vbscript:msgbox(1))
[Exploit File](file:///etc/passwd)
`
    const { container } = render(<SafeMarkdown content={maliciousLinks} />)

    // No link should contain javascript: or data: or file: or vbscript:
    const activeLinks = container.querySelectorAll('a')
    for (const a of activeLinks) {
      const href = a.getAttribute('href') || ''
      expect(href).not.toMatch(/^(javascript:|data:|file:|vbscript:)/i)
    }

    // Neutralized links rendered as non-navigable spans
    const neutralized = container.querySelectorAll('.eureka-markdown-neutralized-link')
    expect(neutralized.length).toBeGreaterThan(0)
  })
})

describe('Citation Artifact Stripping (stripCitationArtifacts)', () => {
  it('strips inline [Source 1], [Source 2], [Source 1, 2] markers and cleans punctuation', () => {
    const input = 'Eureka Solutions is a top NetSuite partner [Source 1]. We offer ERP [Source 1, 2] and Cloud [Source 3].'
    const result = stripCitationArtifacts(input)

    expect(result).toBe('Eureka Solutions is a top NetSuite partner. We offer ERP and Cloud.')
    expect(result).not.toContain('[Source')
  })

  it('strips inline numeric citation markers [1], [2], [1, 2]', () => {
    const input = 'We specialize in AI consulting [1] and cloud migrations [2].'
    const result = stripCitationArtifacts(input)

    expect(result).toBe('We specialize in AI consulting and cloud migrations.')
    expect(result).not.toMatch(/\[\d+\]/)
  })

  it('strips inline [Source: ...] and [Ref: ...] markers', () => {
    const input = 'Our case study demonstrates 70% efficiency gains [Source: Municipality WhatsApp Bot].'
    const result = stripCitationArtifacts(input)

    expect(result).toBe('Our case study demonstrates 70% efficiency gains.')
    expect(result).not.toContain('[Source:')
  })

  it('strips trailing ### Sources, References, and Citations sections', () => {
    const input = `Eureka Solutions provides complete ERP modernization.

### Sources
- [Source 1] NetSuite Implementation: https://eurekasolutions.in/services/netsuite
- [Source 2] Cloud Integration: https://eurekasolutions.in/services/cloud`

    const result = stripCitationArtifacts(input)

    expect(result).toBe('Eureka Solutions provides complete ERP modernization.')
    expect(result).not.toContain('### Sources')
    expect(result).not.toContain('https://eurekasolutions.in/services/netsuite')
  })

  it('strips trailing **References:** section with numbered links', () => {
    const input = `We build tailored business solutions.

**References:**
1. https://eurekasolutions.in/about
2. https://eurekasolutions.in/contact`

    const result = stripCitationArtifacts(input)

    expect(result).toBe('We build tailored business solutions.')
    expect(result).not.toContain('**References:**')
    expect(result).not.toContain('https://eurekasolutions.in/about')
  })

  it('preserves meaningful bracketed text like [CRITICAL], [v1.0.0], and [2024-2026]', () => {
    const input = 'Important notice: [CRITICAL]. Release version: [v2.4.0]. Valid for period [2024-2026].'
    const result = stripCitationArtifacts(input)

    expect(result).toBe('Important notice: [CRITICAL]. Release version: [v2.4.0]. Valid for period [2024-2026].')
  })

  it('preserves code expressions like array[0] and items[1]', () => {
    const input = 'Initialize configuration array[0] and items[1] in the setup routine.'
    const result = stripCitationArtifacts(input)

    expect(result).toBe('Initialize configuration array[0] and items[1] in the setup routine.')
  })

  it('preserves ordered steps: 1. Step one 2. Step two', () => {
    const input = 'Follow these steps:\n1. Initial assessment\n2. Architecture review\n3. Deployment'
    const result = stripCitationArtifacts(input)

    expect(result).toBe('Follow these steps:\n1. Initial assessment\n2. Architecture review\n3. Deployment')
  })

  it('preserves standard markdown links [Title](url)', () => {
    const input = 'Check out [Eureka Services](https://eurekasolutions.in/services) for more details.'
    const result = stripCitationArtifacts(input)

    expect(result).toBe('Check out [Eureka Services](https://eurekasolutions.in/services) for more details.')
  })
})

describe('safeUrlTransform unit test', () => {
  it('permits safe http, https, mailto, and relative URLs', () => {
    expect(safeUrlTransform('https://eurekasolutions.in')).toBe('https://eurekasolutions.in')
    expect(safeUrlTransform('http://example.com')).toBe('http://example.com')
    expect(safeUrlTransform('mailto:info@eurekasolutions.in')).toBe('mailto:info@eurekasolutions.in')
    expect(safeUrlTransform('/services/erp')).toBe('/services/erp')
  })

  it('blocks dangerous schemes', () => {
    expect(safeUrlTransform('javascript:alert(1)')).toBe('')
    expect(safeUrlTransform('JAVASCRIPT:void(0)')).toBe('')
    expect(safeUrlTransform('data:text/html,evil')).toBe('')
    expect(safeUrlTransform('vbscript:msgbox')).toBe('')
    expect(safeUrlTransform('file:///C:/Windows')).toBe('')
  })
})
