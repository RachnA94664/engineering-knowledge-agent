/** One place that talks to the backend. Every error becomes an `ApiError`. */

import type {
  AuditEntry,
  Change,
  ChatResult,
  ConfirmResult,
  Health,
  ImpactReport,
  ProposeResult,
  RejectResult,
  Requirement,
  Risk,
  RiskLevel,
  TestCase,
} from './types'

export const API_URL: string = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(
  /\/+$/,
  '',
)

/** The backend answers errors as {"error": {"code", "message", "details"}}. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>
  /** The raw JSON body of the failed response, when there was one. */
  readonly body: unknown

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
    body: unknown = null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.body = body
  }
}

interface RequestOptions {
  body?: unknown
  signal?: AbortSignal
}

async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers: options.body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(0, 'cancelled', 'The request was cancelled.')
    }
    throw new ApiError(
      0,
      'network_error',
      `Cannot reach the server at ${API_URL}. Is the backend running?`,
    )
  }

  const text = await response.text()
  let data: unknown
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }

  if (!response.ok) {
    const envelope = (data as { error?: { code?: string; message?: string; details?: object } } | null)
      ?.error
    throw new ApiError(
      response.status,
      envelope?.code ?? 'http_error',
      envelope?.message ?? `The server answered ${response.status}.`,
      (envelope?.details as Record<string, unknown> | undefined) ?? {},
      data,
    )
  }
  return data as T
}

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const api = {
  /**
   * 200 means healthy. A 503 also carries a Health body that explains the problem
   * (e.g. "the database schema is out of date ... run 'alembic upgrade head'"), so we
   * return it instead of throwing. Only "cannot reach the server" is an error.
   */
  async health(): Promise<Health> {
    try {
      return await request<Health>('GET', '/health')
    } catch (error) {
      const body = error instanceof ApiError ? (error.body as Partial<Health> | null) : null
      if (error instanceof ApiError && error.status === 503 && body?.status && body.database) {
        return { status: body.status, database: body.database }
      }
      throw error
    }
  },

  listRequirements: () => request<Requirement[]>('GET', '/requirements'),
  getTestCases: (requirementId: string) =>
    request<TestCase[]>('GET', `/requirements/${encodeURIComponent(requirementId)}/test-cases`),

  /** Null when no change to this requirement has been confirmed yet (the backend says 404). */
  async getImpact(requirementId: string): Promise<ImpactReport | null> {
    try {
      return await request<ImpactReport>(
        'GET',
        `/requirements/${encodeURIComponent(requirementId)}/impact`,
      )
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null
      throw error
    }
  },

  listRisks: (filters: { level?: RiskLevel | ''; needsReview?: boolean } = {}) =>
    request<Risk[]>(
      'GET',
      `/risks${query({ level: filters.level, needs_review: filters.needsReview || undefined })}`,
    ),
  markRiskReviewed: (riskId: string, actor: string) =>
    request<Risk>('POST', `/risks/${encodeURIComponent(riskId)}/reviewed`, { body: { actor } }),

  listPending: () => request<Change[]>('GET', '/changes'),
  proposeChange: (requirementId: string, patch: Record<string, unknown>, proposedBy: string) =>
    request<ProposeResult>('POST', '/changes', {
      body: { requirement_id: requirementId, patch, proposed_by: proposedBy },
    }),
  confirmChange: (changeId: number, actor: string) =>
    request<ConfirmResult>('POST', `/changes/${changeId}/confirm`, { body: { actor } }),
  rejectChange: (changeId: number, actor: string) =>
    request<RejectResult>('POST', `/changes/${changeId}/reject`, { body: { actor } }),

  getAuditLog: (filters: { limit?: number; entityId?: string } = {}) =>
    request<AuditEntry[]>(
      'GET',
      `/audit-log${query({ limit: filters.limit, entity_id: filters.entityId })}`,
    ),

  chat: (message: string, signal?: AbortSignal) =>
    request<ChatResult>('POST', '/chat', { body: { message }, signal }),
}
