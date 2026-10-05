import { vi } from 'vitest'
import type { Change, ImpactReport, Requirement, Risk, TestCase } from '../api/types'

export function requirement(overrides: Partial<Requirement> = {}): Requirement {
  return {
    id: 'REQ-001',
    title: 'User login',
    description: 'Users can sign in.',
    priority: 'high',
    status: 'approved',
    version: 1,
    created_at: '2026-01-01T00:00:00+00:00',
    updated_at: '2026-01-01T00:00:00+00:00',
    ...overrides,
  }
}

export function risk(overrides: Partial<Risk> = {}): Risk {
  return {
    id: 'RISK-001',
    title: 'Weak passwords',
    description: 'x',
    severity: 4,
    likelihood: 3,
    status: 'open',
    score: 12,
    level: 'high',
    needs_review: false,
    ...overrides,
  }
}

export function change(overrides: Partial<Change> = {}): Change {
  return {
    id: 7,
    entity_type: 'requirement',
    entity_id: 'REQ-001',
    patch: { priority: 'critical' },
    base_version: 1,
    proposed_by: 'agent',
    status: 'pending',
    created_at: '2026-01-02T00:00:00+00:00',
    resolved_at: null,
    ...overrides,
  }
}

export function testCase(overrides: Partial<TestCase> = {}): TestCase {
  return {
    id: 'TC-001',
    requirement_id: 'REQ-001',
    title: 'Login works',
    steps: 's',
    expected_result: 'e',
    status: 'pass',
    ...overrides,
  }
}

export function impact(overrides: Partial<ImpactReport> = {}): ImpactReport {
  return {
    id: 1,
    change_id: 7,
    created_at: '2026-01-03T00:00:00+00:00',
    requirement_id: 'REQ-001',
    level: 'medium',
    changed_fields: { priority: { old: 'high', new: 'critical' } },
    tests_to_reset: [],
    tests_failing: [],
    risks_to_flag: [{ id: 'RISK-001', title: 'Weak passwords', score: 12, level: 'high', status: 'open', already_flagged: false }],
    warnings: [],
    summary: 'Priority raised: 1 risk flagged for review.',
    ...overrides,
  }
}

type Handler = (body: unknown) => { status?: number; body?: unknown } | unknown

/**
 * Replace `fetch` with a tiny fake backend. Keys look like "GET /requirements".
 * A handler returns the JSON body, or { status, body } for a non-200 answer.
 * Any call nobody handled fails the test loudly instead of silently returning nothing.
 */
export function mockApi(routes: Record<string, Handler>) {
  const calls: { key: string; body: unknown }[] = []
  const fake = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input))
    const key = `${init?.method ?? 'GET'} ${url.pathname}`
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ key, body })
    const handler = routes[key]
    if (!handler) throw new Error(`Unexpected request: ${key}`)
    const result = handler(body) as { status?: number; body?: unknown } | undefined
    // { status: 409, body } is an explicit HTTP answer; a body like { status: 'ok' } is not.
    const explicit =
      result !== null && typeof result === 'object' && typeof result.status === 'number'
    const status = explicit ? (result.status as number) : 200
    const payload = explicit ? result.body : result
    return new Response(JSON.stringify(payload ?? null), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fake)
  return { calls, fake }
}

export const HEALTHY = { 'GET /health': () => ({ status: 'ok', database: 'ok' }) }
