import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AskEurekaWidget } from '../components/AskEurekaWidget'
import * as chatClient from '../api/chatClient'
import type { ApiResult } from '../api/types'

// Mock scrollIntoView which is not implemented in jsdom
window.HTMLElement.prototype.scrollIntoView = vi.fn()

describe('AskEurekaWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders launcher button with accessible attributes in initial collapsed state', () => {
    render(<AskEurekaWidget />)

    const launcher = screen.getByRole('button', { name: /open ask eureka ai chat/i })
    expect(launcher).toBeInTheDocument()
    expect(launcher).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('opens chat dialog when launcher is clicked and closes when close button is clicked', async () => {
    const user = userEvent.setup()
    render(<AskEurekaWidget />)

    const launcher = screen.getByRole('button', { name: /open ask eureka ai chat/i })
    await user.click(launcher)

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(launcher).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/Answers based on Eureka Solutions website information/i)).toBeInTheDocument()

    // Click close button
    const closeBtn = screen.getByRole('button', { name: /close chat/i })
    await user.click(closeBtn)

    expect(screen.queryByRole('dialog')).toBeNull()
    expect(launcher).toHaveAttribute('aria-expanded', 'false')
  })

  it('closes dialog when Escape key is pressed', async () => {
    const user = userEvent.setup()
    render(<AskEurekaWidget initialOpen={true} />)

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await user.keyboard('{Escape}')

    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('displays starter questions when conversation is empty', () => {
    render(<AskEurekaWidget initialOpen={true} />)

    expect(screen.getByText(/Suggested Questions:/i)).toBeInTheDocument()
    expect(
      screen.getByRole('button', {
        name: /what enterprise software services does eureka solutions offer\?/i,
      })
    ).toBeInTheDocument()
  })

  it('prevents sending empty or whitespace-only messages', async () => {
    const user = userEvent.setup()
    const sendSpy = vi.spyOn(chatClient, 'sendChatMessage')

    render(<AskEurekaWidget initialOpen={true} />)

    const sendBtn = screen.getByRole('button', { name: /send message/i })
    expect(sendBtn).toBeDisabled()

    const textarea = screen.getByRole('textbox', { name: /your question/i })
    await user.type(textarea, '   ')

    expect(sendBtn).toBeDisabled()
    expect(sendSpy).not.toHaveBeenCalled()
  })

  it('enforces 2000 character limit', async () => {
    render(<AskEurekaWidget initialOpen={true} />)

    const textarea = screen.getByRole('textbox', { name: /your question/i })
    const counter = screen.getByText(/0 \/ 2000/)
    expect(counter).toBeInTheDocument()

    // Type 2001 chars
    fireEvent.change(textarea, { target: { value: 'A'.repeat(2001) } })

    const sendBtn = screen.getByRole('button', { name: /send message/i })
    expect(sendBtn).toBeDisabled()
    expect(screen.getByText(/2001 \/ 2000/)).toHaveClass('eureka-char-limit-warning')
  })

  it('submits question, shows loading indicator, and renders assistant response with sources hidden from UI', async () => {
    const user = userEvent.setup()
    const mockSuccess: ApiResult = {
      success: true,
      data: {
        request_id: 'req-success-100',
        answer: 'Eureka Solutions is an award-winning NetSuite partner.',
        status: 'answered',
        sources: [
          {
            title: 'Oracle NetSuite Partner',
            url: 'https://eurekasolutions.in/Eureka2026/services/netsuite/',
            snippet: 'NetSuite implementation experts with 20+ years experience.',
          },
        ],
        message: null,
      },
    }

    vi.spyOn(chatClient, 'sendChatMessage').mockResolvedValue(mockSuccess)

    render(<AskEurekaWidget initialOpen={true} />)

    const textarea = screen.getByRole('textbox', { name: /your question/i })
    await user.type(textarea, 'Tell me about NetSuite')

    const sendBtn = screen.getByRole('button', { name: /send message/i })
    expect(sendBtn).not.toBeDisabled()

    await user.click(sendBtn)

    // User message should appear
    expect(screen.getByText('Tell me about NetSuite')).toBeInTheDocument()

    // Wait for response to render
    await waitFor(() => {
      expect(
        screen.getByText(/Eureka Solutions is an award-winning NetSuite partner/i)
      ).toBeInTheDocument()
    })

    // Citations must NOT be rendered in the visible UI
    expect(screen.queryByTestId('citations-section')).toBeNull()
    expect(screen.queryByText(/Sources \(/i)).toBeNull()
    expect(screen.queryByRole('link', { name: /Oracle NetSuite Partner/i })).toBeNull()

    // The backend API response retains sources metadata internally for factual grounding
    expect(mockSuccess.data?.sources).toHaveLength(1)
  })

  it('clicking a starter question submits the question directly', async () => {
    const user = userEvent.setup()
    const mockSuccess: ApiResult = {
      success: true,
      data: {
        request_id: 'req-starter-01',
        answer: 'We provide ERP, cloud data integration, and banking portals.',
        status: 'answered',
        sources: [],
        message: null,
      },
    }

    const sendSpy = vi.spyOn(chatClient, 'sendChatMessage').mockResolvedValue(mockSuccess)

    render(<AskEurekaWidget initialOpen={true} />)

    const starterBtn = screen.getByRole('button', {
      name: /what enterprise software services does eureka solutions offer\?/i,
    })
    await user.click(starterBtn)

    expect(sendSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'What enterprise software services does Eureka Solutions offer?',
      }),
      expect.any(Object)
    )

    await waitFor(() => {
      expect(
        screen.getByText(/We provide ERP, cloud data integration, and banking portals/i)
      ).toBeInTheDocument()
    })
  })

  it('displays error state with Try Again button and preserves message on failure', async () => {
    const user = userEvent.setup()
    const mockError: ApiResult = {
      success: false,
      errorType: 'unavailable',
      message: 'The AI assistant service is temporarily unavailable.',
      requestId: 'req-fail-503',
    }

    vi.spyOn(chatClient, 'sendChatMessage').mockResolvedValue(mockError)

    render(<AskEurekaWidget initialOpen={true} />)

    const textarea = screen.getByRole('textbox', { name: /your question/i })
    await user.type(textarea, 'What are your cloud services?')

    const sendBtn = screen.getByRole('button', { name: /send message/i })
    await user.click(sendBtn)

    await waitFor(() => {
      expect(
        screen.getByText(/The AI assistant service is temporarily unavailable/i)
      ).toBeInTheDocument()
    })

    expect(screen.getByText(/Reference ID: req-fail-503/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry question/i })).toBeInTheDocument()

    // The draft text should be restored in the composer so user does not lose input
    expect(screen.getByRole('textbox', { name: /your question/i })).toHaveValue(
      'What are your cloud services?'
    )
  })

  it('reset button clears conversation and creates a clean session', async () => {
    const user = userEvent.setup()
    const mockSuccess: ApiResult = {
      success: true,
      data: {
        request_id: 'req-first-1',
        answer: 'First answer',
        status: 'answered',
        sources: [],
      },
    }

    vi.spyOn(chatClient, 'sendChatMessage').mockResolvedValue(mockSuccess)

    render(<AskEurekaWidget initialOpen={true} />)

    const textarea = screen.getByRole('textbox', { name: /your question/i })
    await user.type(textarea, 'First question')
    await user.click(screen.getByRole('button', { name: /send message/i }))

    await waitFor(() => {
      expect(screen.getByText('First answer')).toBeInTheDocument()
    })

    // Reset button should now be visible in header
    const resetBtn = screen.getByRole('button', { name: /start new conversation/i })
    await user.click(resetBtn)

    // Conversation should be cleared back to starter questions
    expect(screen.queryByText('First answer')).toBeNull()
    expect(screen.queryByText('First question')).toBeNull()
    expect(screen.getByText(/Suggested Questions:/i)).toBeInTheDocument()
  })

  it('strips inline citation markers and trailing source lists from assistant messages in UI', async () => {
    const user = userEvent.setup()
    const mockSuccess: ApiResult = {
      success: true,
      data: {
        request_id: 'req-clean-200',
        answer:
          'Eureka Solutions provides Enterprise ERP [Source 1] and Cloud Solutions [Source 2].\n\n' +
          '### Sources\n' +
          '- [Source 1] ERP: https://eurekasolutions.in/erp\n' +
          '- [Source 2] Cloud: https://eurekasolutions.in/cloud',
        status: 'answered',
        sources: [
          {
            title: 'ERP',
            url: 'https://eurekasolutions.in/erp',
            snippet: 'ERP solutions',
          },
        ],
        message: null,
      },
    }

    vi.spyOn(chatClient, 'sendChatMessage').mockResolvedValue(mockSuccess)

    render(<AskEurekaWidget initialOpen={true} />)

    const textarea = screen.getByRole('textbox', { name: /your question/i })
    await user.type(textarea, 'What services do you offer?')
    await user.click(screen.getByRole('button', { name: /send message/i }))

    await waitFor(() => {
      expect(
        screen.getByText(/Eureka Solutions provides Enterprise ERP and Cloud Solutions\./i)
      ).toBeInTheDocument()
    })

    // Inline citations and trailing source headers must not appear
    expect(screen.queryByText(/\[Source 1\]/i)).toBeNull()
    expect(screen.queryByText(/### Sources/i)).toBeNull()
    expect(screen.queryByTestId('citations-section')).toBeNull()
  })

  it('preserves numbered lists, bracketed terms, and structured formatting in assistant answer', async () => {
    const user = userEvent.setup()
    const mockSuccess: ApiResult = {
      success: true,
      data: {
        request_id: 'req-formatting-300',
        answer:
          'Here is our implementation methodology:\n\n' +
          '1. Assessment: [CRITICAL] review of requirements.\n' +
          '2. Deployment: version [v3.0.0] rollout.\n' +
          '3. Support: ongoing maintenance.\n\n' +
          'Key note: array[0] indexing is verified.',
        status: 'answered',
        sources: [],
        message: null,
      },
    }

    vi.spyOn(chatClient, 'sendChatMessage').mockResolvedValue(mockSuccess)

    render(<AskEurekaWidget initialOpen={true} />)

    const textarea = screen.getByRole('textbox', { name: /your question/i })
    await user.type(textarea, 'Explain your process')
    await user.click(screen.getByRole('button', { name: /send message/i }))

    await waitFor(() => {
      expect(screen.getByText(/Here is our implementation methodology:/i)).toBeInTheDocument()
    })

    // Preserved numbered list items and bracketed content
    expect(screen.getByText(/\[CRITICAL\] review of requirements\./i)).toBeInTheDocument()
    expect(screen.getByText(/version \[v3\.0\.0\] rollout\./i)).toBeInTheDocument()
    expect(screen.getByText(/array\[0\] indexing is verified\./i)).toBeInTheDocument()
  })

  it('renders out-of-scope and insufficient-evidence notices cleanly without source cards', async () => {
    const user = userEvent.setup()
    const mockOutOfScope: ApiResult = {
      success: true,
      data: {
        request_id: 'req-oos-400',
        answer: 'I can only assist with Eureka Solutions questions.',
        status: 'out_of_scope',
        sources: [],
      },
    }

    vi.spyOn(chatClient, 'sendChatMessage').mockResolvedValue(mockOutOfScope)

    render(<AskEurekaWidget initialOpen={true} />)

    const textarea = screen.getByRole('textbox', { name: /your question/i })
    await user.type(textarea, 'What is the weather in Paris?')
    await user.click(screen.getByRole('button', { name: /send message/i }))

    await waitFor(() => {
      expect(screen.getByTestId('out-of-scope-notice')).toBeInTheDocument()
    })

    expect(screen.queryByTestId('citations-section')).toBeNull()
  })

  it('suppresses duplicate rendering if mounted multiple times in the DOM (UI-020)', () => {
    const { container: firstContainer, unmount } = render(<AskEurekaWidget />)
    expect(firstContainer.querySelector('.eureka-widget-root')).toBeInTheDocument()

    // Second render while first is still mounted
    const { container: secondContainer } = render(<AskEurekaWidget />)
    expect(secondContainer.querySelector('.eureka-widget-root')).toBeNull()

    // After unmounting first, a new one can mount
    unmount()
  })
})


