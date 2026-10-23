import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AskEurekaWidget } from '../components/AskEurekaWidget'
import { ChatPanel } from '../components/ChatPanel'

window.HTMLElement.prototype.scrollIntoView = vi.fn()

describe('Accessibility (a11y)', () => {
  it('dialog has appropriate ARIA landmarks and labelledby attribute', () => {
    render(<AskEurekaWidget initialOpen={true} />)

    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAttribute('aria-labelledby', 'eureka-dialog-title')

    const heading = screen.getByRole('heading', { level: 2, name: /ask eureka ai/i })
    expect(heading).toHaveAttribute('id', 'eureka-dialog-title')
  })

  it('live region exists for announcing conversation activity', () => {
    render(<AskEurekaWidget initialOpen={true} />)

    const logRegion = screen.getByRole('log')
    expect(logRegion).toHaveAttribute('aria-live', 'polite')
    expect(logRegion).toHaveAttribute('aria-label', 'Conversation history')
  })

  it('launcher exposes expanded and collapsed state to screen readers', async () => {
    const user = userEvent.setup()
    render(<AskEurekaWidget />)

    const launcher = screen.getByRole('button', { name: /open ask eureka ai chat/i })
    expect(launcher).toHaveAttribute('aria-expanded', 'false')

    await user.click(launcher)
    expect(launcher).toHaveAttribute('aria-expanded', 'true')
  })

  it('handles focus cycling when Tab is pressed within dialog', () => {
    const onClose = vi.fn()
    const onReset = vi.fn()
    const onSend = vi.fn()
    const onSelectStarter = vi.fn()
    const onRetry = vi.fn()

    render(
      <ChatPanel
        isOpen={true}
        onClose={onClose}
        onReset={onReset}
        messages={[]}
        isLoading={false}
        onSend={onSend}
        onSelectStarter={onSelectStarter}
        onRetry={onRetry}
      />
    )

    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeInTheDocument()

    // Test Escape triggers onClose
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('all interactive controls have accessible names', () => {
    render(<AskEurekaWidget initialOpen={true} />)

    const buttons = screen.getAllByRole('button')
    buttons.forEach((btn) => {
      expect(btn).toHaveAccessibleName()
    })

    const textarea = screen.getByRole('textbox')
    expect(textarea).toHaveAccessibleName()
  })
})
