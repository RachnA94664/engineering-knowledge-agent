import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import {
  change,
  HEALTHY,
  impact,
  mockApi,
  requirement,
  risk,
  testCase,
} from './test/fakeApi'

afterEach(() => vi.unstubAllGlobals())

function chatResult(overrides: Record<string, unknown> = {}) {
  return {
    answer: 'REQ-002 has no test cases.',
    intent: 'query',
    grounded: true,
    refused: false,
    records: [{ id: 'REQ-002', title: 'Password reset' }],
    tool_calls: [{ name: 'find_requirements_without_tests', arguments: {}, ok: true, error: null }],
    pending_changes: [],
    ...overrides,
  }
}

describe('health banner', () => {
  it('tells the user how to fix a database that is behind the code', async () => {
    mockApi({
      'GET /health': () => ({
        status: 503,
        body: { status: 'error', database: "out of date: run 'alembic upgrade head'" },
      }),
      'GET /changes': () => [],
    })
    render(<App />)
    expect(await screen.findByText(/alembic upgrade head/)).toBeInTheDocument()
  })

  it('says so when the backend cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    render(<App />)
    expect(await screen.findByText(/Cannot reach the backend/)).toBeInTheDocument()
  })
})

describe('chat', () => {
  it('shows the answer, its verdict and the records behind it', async () => {
    mockApi({ ...HEALTHY, 'GET /changes': () => [], 'POST /chat': () => chatResult() })
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByLabelText('Your message'), 'Which requirements have no tests?{Enter}')
    expect(await screen.findByText('REQ-002 has no test cases.')).toBeInTheDocument()
    expect(screen.getByText('Checked against the database')).toBeInTheDocument()
    expect(screen.getByText(/Records behind this answer/)).toBeInTheDocument()
  })

  it('marks an answer that could not be checked as not verified', async () => {
    mockApi({
      ...HEALTHY,
      'GET /changes': () => [],
      'POST /chat': () => chatResult({ grounded: false }),
    })
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByLabelText('Your message'), 'hello{Enter}')
    expect(await screen.findByText('Not verified')).toBeInTheDocument()
  })

  it('shows a friendly message when the server fails', async () => {
    mockApi({
      ...HEALTHY,
      'GET /changes': () => [],
      'POST /chat': () => ({
        status: 503,
        body: { error: { code: 'service_unavailable', message: 'The AI service is unavailable.', details: {} } },
      }),
    })
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByLabelText('Your message'), 'hello{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent('The AI service is unavailable.')
  })

  it('blocks messages over the length limit', async () => {
    mockApi({ ...HEALTHY, 'GET /changes': () => [] })
    render(<App />)
    const box = screen.getByLabelText('Your message')
    await userEvent.setup().click(box)
    await userEvent.setup().paste('x'.repeat(1001))
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
  })

  it('lets the person confirm a proposed change and shows the impact', async () => {
    const proposed = change()
    mockApi({
      ...HEALTHY,
      'GET /changes': () => [],
      'POST /chat': () =>
        chatResult({
          intent: 'update',
          answer: 'I proposed it.',
          pending_changes: [{ change: proposed, preview: { priority: { old: 'high', new: 'critical' } } }],
        }),
      'POST /changes/7/confirm': () => ({
        change: { ...proposed, status: 'applied' },
        already_applied: false,
        requirement: requirement({ priority: 'critical' }),
        impact: impact(),
      }),
    })
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByPlaceholderText('used in the audit log'), 'Rachna')
    await user.type(screen.getByLabelText('Your message'), 'Set REQ-001 priority to critical{Enter}')
    await user.click(await screen.findByRole('button', { name: 'Confirm change' }))
    expect(await screen.findByText(/Priority raised: 1 risk flagged/)).toBeInTheDocument()
    expect(screen.getByText(/impact analysis ran automatically/)).toBeInTheDocument()
  })

  it('cannot confirm without a name', async () => {
    const proposed = change()
    mockApi({
      ...HEALTHY,
      'GET /changes': () => [],
      'POST /chat': () =>
        chatResult({
          pending_changes: [{ change: proposed, preview: { priority: { old: 'high', new: 'critical' } } }],
        }),
    })
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByLabelText('Your message'), 'x{Enter}')
    expect(await screen.findByRole('button', { name: 'Confirm change' })).toBeDisabled()
  })
})

describe('pending page', () => {
  it('explains that an out-of-date proposal must be proposed again (409)', async () => {
    window.location.hash = '#/pending'
    mockApi({
      ...HEALTHY,
      'GET /changes': () => [change()],
      'GET /requirements': () => [requirement()],
      'POST /changes/7/confirm': () => ({
        status: 409,
        body: { error: { code: 'conflict', message: 'REQ-001 changed since this was proposed.', details: {} } },
      }),
    })
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByPlaceholderText('used in the audit log'), 'Rachna')
    await user.click(await screen.findByRole('button', { name: 'Confirm change' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('propose it again')
  })

  it('shows the current value next to the proposed one', async () => {
    window.location.hash = '#/pending'
    mockApi({
      ...HEALTHY,
      'GET /changes': () => [change()],
      'GET /requirements': () => [requirement({ priority: 'high' })],
    })
    render(<App />)
    const card = await screen.findByLabelText('Proposed change 7')
    expect(within(card).getByText('high')).toBeInTheDocument()
    expect(within(card).getByText('critical')).toBeInTheDocument()
  })

  it('keeps a confirmed card, with its impact, after the list reloads', async () => {
    window.location.hash = '#/pending'
    let confirmed = false
    mockApi({
      ...HEALTHY,
      'GET /changes': () => (confirmed ? [] : [change()]),
      'GET /requirements': () => [requirement()],
      'POST /changes/7/confirm': () => {
        confirmed = true
        return { change: change({ status: 'applied' }), already_applied: false, requirement: requirement(), impact: impact() }
      },
    })
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByPlaceholderText('used in the audit log'), 'Rachna')
    await user.click(await screen.findByRole('button', { name: 'Confirm change' }))
    expect(await screen.findByText(/Priority raised/)).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText(/Nothing is waiting/)).not.toBeInTheDocument())
    expect(screen.getByText(/Priority raised/)).toBeInTheDocument()
  })

  it('shows an empty state', async () => {
    window.location.hash = '#/pending'
    mockApi({ ...HEALTHY, 'GET /changes': () => [], 'GET /requirements': () => [] })
    render(<App />)
    expect(await screen.findByText('Nothing is waiting for review.')).toBeInTheDocument()
  })
})

describe('risks page', () => {
  it('marks a risk as reviewed with the person\'s name', async () => {
    window.location.hash = '#/risks'
    const { calls } = mockApi({
      ...HEALTHY,
      'GET /changes': () => [],
      'GET /risks': () => [risk({ needs_review: true })],
      'POST /risks/RISK-001/reviewed': () => risk({ needs_review: false }),
    })
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByPlaceholderText('used in the audit log'), 'Rachna')
    await user.click(await screen.findByRole('button', { name: 'Mark reviewed' }))
    await waitFor(() =>
      expect(calls.find((call) => call.key === 'POST /risks/RISK-001/reviewed')?.body).toEqual({
        actor: 'Rachna',
      }),
    )
  })
})

describe('requirements page', () => {
  function setup() {
    window.location.hash = '#/requirements'
    return mockApi({
      ...HEALTHY,
      'GET /changes': () => [],
      'GET /requirements': () => [requirement(), requirement({ id: 'REQ-002', title: 'Password reset', status: 'draft' })],
      'GET /requirements/REQ-001/test-cases': () => [testCase()],
      'GET /requirements/REQ-001/impact': () => ({
        status: 404,
        body: { error: { code: 'not_found', message: 'none', details: {} } },
      }),
      'POST /changes': (body) => ({ change: change(), preview: (body as { patch: object }).patch }),
    })
  }

  it('filters the list by search text', async () => {
    setup()
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('Password reset')
    await user.type(screen.getByLabelText('Search'), 'login')
    expect(screen.queryByText('Password reset')).not.toBeInTheDocument()
    expect(screen.getByText('User login')).toBeInTheDocument()
  })

  it('offers only the status moves the rules allow', async () => {
    setup()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'REQ-001' }))
    const status = await screen.findByLabelText('Status', { selector: 'form select' })
    const options = within(status).getAllByRole('option').map((option) => option.textContent)
    expect(options).toContain('Move to implemented')
    expect(options).not.toContain('Move to draft')
  })

  it('proposes a change but does not apply it', async () => {
    const { calls } = setup()
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByPlaceholderText('used in the audit log'), 'Rachna')
    await user.click(await screen.findByRole('button', { name: 'REQ-001' }))
    await user.selectOptions(await screen.findByLabelText('Priority', { selector: 'form select' }), 'critical')
    await user.click(screen.getByRole('button', { name: 'Propose change' }))
    await waitFor(() =>
      expect(calls.find((call) => call.key === 'POST /changes')?.body).toEqual({
        requirement_id: 'REQ-001',
        patch: { priority: 'critical' },
        proposed_by: 'Rachna',
      }),
    )
    expect(calls.some((call) => call.key.includes('/confirm'))).toBe(false)
  })

  it('shows a message instead of an impact card when there is none yet', async () => {
    setup()
    render(<App />)
    await userEvent.setup().click(await screen.findByRole('button', { name: 'REQ-001' }))
    expect(await screen.findByText(/no impact report/)).toBeInTheDocument()
  })
})

describe('audit page', () => {
  it('lists entries with who and what', async () => {
    window.location.hash = '#/audit'
    mockApi({
      ...HEALTHY,
      'GET /changes': () => [],
      'GET /audit-log': () => [
        {
          id: 1,
          ts: '2026-01-01T00:00:00+00:00',
          actor: 'impact-analysis',
          source: 'system',
          entity_type: 'risk',
          entity_id: 'RISK-001',
          action: 'flag_for_review',
          old_value: false,
          new_value: true,
          request_id: null,
        },
      ],
    })
    render(<App />)
    expect(await screen.findByText('impact-analysis')).toBeInTheDocument()
    expect(screen.getByText('RISK-001')).toBeInTheDocument()
  })
})
