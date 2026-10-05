import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from './client'
import { mockApi } from '../test/fakeApi'

afterEach(() => vi.unstubAllGlobals())

describe('api client', () => {
  it('turns the backend error envelope into an ApiError', async () => {
    mockApi({
      'POST /changes/3/confirm': () => ({
        status: 409,
        body: { error: { code: 'conflict', message: 'The record changed.', details: { x: 1 } } },
      }),
    })
    const error = await api.confirmChange(3, 'rachna').catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 409, code: 'conflict', message: 'The record changed.' })
  })

  it('explains a network failure instead of showing a stack trace', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(api.listRequirements()).rejects.toMatchObject({
      code: 'network_error',
      message: expect.stringContaining('Is the backend running?'),
    })
  })

  it('reports a cancelled request as "cancelled"', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('x', 'AbortError')))
    await expect(api.chat('hi')).rejects.toMatchObject({ code: 'cancelled' })
  })

  it('returns null when a requirement has no impact report yet (404)', async () => {
    mockApi({
      'GET /requirements/REQ-001/impact': () => ({
        status: 404,
        body: { error: { code: 'not_found', message: 'none', details: {} } },
      }),
    })
    await expect(api.getImpact('REQ-001')).resolves.toBeNull()
  })

  it('keeps a 5xx on the impact route as an error', async () => {
    mockApi({ 'GET /requirements/REQ-001/impact': () => ({ status: 500, body: null }) })
    await expect(api.getImpact('REQ-001')).rejects.toMatchObject({ status: 500 })
  })

  it('returns the health body of a 503 so the UI can show the fix', async () => {
    mockApi({
      'GET /health': () => ({
        status: 503,
        body: { status: 'error', database: "schema is out of date: run 'alembic upgrade head'" },
      }),
    })
    await expect(api.health()).resolves.toEqual({
      status: 'error',
      database: "schema is out of date: run 'alembic upgrade head'",
    })
  })

  it('sends filters as a query string and skips empty ones', async () => {
    const { calls, fake } = mockApi({ 'GET /risks': () => [] })
    await api.listRisks({ level: '', needsReview: true })
    expect(String(fake.mock.calls[0][0])).toMatch(/\/risks\?needs_review=true$/)
    expect(calls).toHaveLength(1)
  })
})
