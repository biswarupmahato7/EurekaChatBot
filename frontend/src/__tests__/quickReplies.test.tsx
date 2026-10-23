import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QuickReplies } from '../components/QuickReplies'
import { AskEurekaWidget } from '../components/AskEurekaWidget'
import * as chatClient from '../api/chatClient'
import type { ApiResult } from '../api/types'

// Mock scrollIntoView which is not implemented in jsdom
window.HTMLElement.prototype.scrollIntoView = vi.fn()

describe('QuickReplies Component & Context-Aware Clarification UX', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ===========================================================================
  // SCENARIO 11: Quick-reply keyboard accessibility
  // ===========================================================================
  it('Scenario 11: renders accessible buttons with role=group and handles keyboard navigation (Enter & Space)', async () => {
    const handleSelect = vi.fn()
    const options = ['Discuss a project', 'Ask about services', 'Something else']

    render(<QuickReplies options={options} onSelect={handleSelect} />)

    const group = screen.getByRole('group', { name: /quick reply options/i })
    expect(group).toBeInTheDocument()

    const chips = screen.getAllByTestId('quick-reply-chip')
    expect(chips).toHaveLength(3)

    // Test tab navigation and Enter key activation
    chips[0].focus()
    expect(document.activeElement).toBe(chips[0])

    fireEvent.keyDown(chips[0], { key: 'Enter', code: 'Enter' })
    expect(handleSelect).toHaveBeenCalledWith('Discuss a project')

    // Test Space key activation
    fireEvent.keyDown(chips[1], { key: ' ', code: 'Space' })
    expect(handleSelect).toHaveBeenCalledWith('Ask about services')
  })

  // ===========================================================================
  // SCENARIO 12: Repeated clicking and duplicate submission prevention
  // ===========================================================================
  it('Scenario 12: prevents duplicate submissions and respects disabled state', async () => {
    const handleSelect = vi.fn()
    const options = ['Discuss a project', 'Ask about services']

    const { rerender } = render(
      <QuickReplies options={options} onSelect={handleSelect} disabled={false} />
    )

    const chips = screen.getAllByTestId('quick-reply-chip')
    fireEvent.click(chips[0])
    expect(handleSelect).toHaveBeenCalledTimes(1)

    // Rerender as disabled (when request is in flight)
    rerender(<QuickReplies options={options} onSelect={handleSelect} disabled={true} />)

    const disabledChips = screen.getAllByTestId('quick-reply-chip')
    expect(disabledChips[0]).toBeDisabled()
    expect(disabledChips[1]).toBeDisabled()

    // Subsequent clicks should not invoke onSelect
    fireEvent.click(disabledChips[0])
    fireEvent.click(disabledChips[1])
    expect(handleSelect).toHaveBeenCalledTimes(1)
  })

  // ===========================================================================
  // SCENARIO 13: Mobile responsiveness and layout classes
  // ===========================================================================
  it('Scenario 13: includes mobile-friendly flex wrap container and chip styling', () => {
    const handleSelect = vi.fn()
    const options = ['Discuss a project', 'Ask about services', 'Business partnership', 'General enquiry', 'Something else']

    const { container } = render(
      <QuickReplies options={options} onSelect={handleSelect} />
    )

    const group = container.querySelector('.eureka-quick-replies')
    expect(group).not.toBeNull()

    const chips = container.querySelectorAll('.eureka-quick-reply-chip')
    expect(chips).toHaveLength(5)
  })

  // ===========================================================================
  // SCENARIO 14: API errors after selecting an option
  // ===========================================================================
  it('Scenario 14: handles API error after selecting a quick reply and enables retry', async () => {
    const user = userEvent.setup()

    // Mock initial contact inquiry returning quick-reply chips
    const contactResult: ApiResult = {
      success: true,
      data: {
        request_id: 'req-01',
        answer: 'You can reach Eureka Solutions at info@eurekasolutions.in. What would you like to connect about?',
        status: 'answered',
        sources: [],
        quick_replies: ['Discuss a project', 'Ask about services', 'Something else'],
      },
    }

    // Mock second call returning 503 error
    const errorResult: ApiResult = {
      success: false,
      errorType: 'unavailable',
      message: 'The AI assistant service is temporarily unavailable. Please try again shortly.',
      requestId: 'req-err-503',
    }

    const spy = vi
      .spyOn(chatClient, 'sendChatMessage')
      .mockResolvedValueOnce(contactResult)
      .mockResolvedValueOnce(errorResult)

    render(<AskEurekaWidget initialOpen={true} />)

    // Send initial contact inquiry
    const input = screen.getByRole('textbox', { name: /your question/i })
    await user.type(input, 'How can I reach out to them?')
    const sendButton = screen.getByRole('button', { name: /send message/i })
    await user.click(sendButton)

    // Verify quick replies render
    await waitFor(() => {
      expect(screen.getByText(/What would you like to connect about\?/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Discuss a project' })).toBeInTheDocument()
    })

    // Click 'Discuss a project' chip
    const chip = screen.getByRole('button', { name: 'Discuss a project' })
    await user.click(chip)

    // Error notice should appear with retry option
    await waitFor(() => {
      expect(screen.getByText(/The AI assistant service is temporarily unavailable/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /retry question/i })).toBeInTheDocument()
    })

    expect(spy).toHaveBeenCalledTimes(2)
  })

  // ===========================================================================
  // SCENARIO 15: User selects "Something else" in chat flow
  // ===========================================================================
  it('Scenario 15: handles user selecting "Something else" and displays open clarification', async () => {
    const user = userEvent.setup()

    const initialResult: ApiResult = {
      success: true,
      data: {
        request_id: 'req-01',
        answer: 'You can reach info@eurekasolutions.in. What would you like to connect with the team about?',
        status: 'answered',
        sources: [],
        quick_replies: ['Discuss a project', 'Ask about services', 'Something else'],
      },
    }

    const somethingElseResult: ApiResult = {
      success: true,
      data: {
        request_id: 'req-02',
        answer: 'Understood! Please tell me a bit more about what you have in mind or what questions you have about Eureka Solutions.',
        status: 'answered',
        sources: [],
        quick_replies: [],
      },
    }

    vi.spyOn(chatClient, 'sendChatMessage')
      .mockResolvedValueOnce(initialResult)
      .mockResolvedValueOnce(somethingElseResult)

    render(<AskEurekaWidget initialOpen={true} />)

    const input = screen.getByRole('textbox', { name: /your question/i })
    await user.type(input, 'How can I contact you?')
    await user.click(screen.getByRole('button', { name: /send message/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Something else' })).toBeInTheDocument()
    })

    // Click "Something else"
    await user.click(screen.getByRole('button', { name: 'Something else' }))

    await waitFor(() => {
      expect(
        screen.getByText(/Understood! Please tell me a bit more about what you have in mind/i)
      ).toBeInTheDocument()
    })
  })
})
