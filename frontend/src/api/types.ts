/** The shapes the backend returns. They mirror backend/app/api/schemas.py. */

export type Priority = 'low' | 'medium' | 'high' | 'critical'
export type RequirementStatus = 'draft' | 'approved' | 'implemented' | 'verified' | 'obsolete'
export type TestStatus = 'not_run' | 'pass' | 'fail' | 'blocked'
export type RiskLevel = 'low' | 'medium' | 'high'

export interface Requirement {
  id: string
  title: string
  description: string
  priority: Priority
  status: RequirementStatus
  version: number
  created_at: string | null
  updated_at: string | null
}

export interface TestCase {
  id: string
  requirement_id: string
  title: string
  steps: string
  expected_result: string
  status: TestStatus
}

export interface Risk {
  id: string
  title: string
  description: string
  severity: number
  likelihood: number
  status: string
  score: number
  level: RiskLevel
  needs_review: boolean
}

export interface Change {
  id: number
  entity_type: string
  entity_id: string
  patch: Record<string, unknown>
  base_version: number
  proposed_by: string
  status: 'pending' | 'applied' | 'rejected' | 'expired'
  created_at: string | null
  resolved_at: string | null
}

export type Preview = Record<string, { old: unknown; new: unknown }>

export interface ProposeResult {
  change: Change
  preview: Preview
}

export interface ImpactReport {
  id: number
  change_id: number
  created_at: string | null
  requirement_id: string
  level: RiskLevel
  changed_fields: Record<string, { old: unknown; new: unknown }>
  tests_to_reset: { id: string; title: string; old_status: string; new_status: string }[]
  tests_failing: { id: string; title: string; status: string }[]
  risks_to_flag: {
    id: string
    title: string
    score: number
    level: RiskLevel
    status: string
    already_flagged: boolean
  }[]
  warnings: string[]
  summary: string
}

export interface ConfirmResult {
  change: Change
  already_applied: boolean
  requirement: Requirement | null
  impact: ImpactReport | null
}

export interface RejectResult {
  change: Change
  already_rejected: boolean
}

export interface AuditEntry {
  id: number
  ts: string | null
  actor: string
  source: 'ui' | 'agent' | 'system'
  entity_type: string
  entity_id: string
  action: string
  old_value: unknown
  new_value: unknown
  request_id: string | null
}

export interface ToolCall {
  name: string
  arguments: Record<string, unknown>
  ok: boolean
  error: string | null
}

export interface PendingProposal {
  change: Change
  preview: Preview
}

export interface ChatResult {
  answer: string
  intent: 'query' | 'update' | 'analysis' | 'out_of_scope' | 'refused'
  grounded: boolean
  refused: boolean
  records: Record<string, unknown>[]
  tool_calls: ToolCall[]
  pending_changes: PendingProposal[]
}

export interface Health {
  status: string
  database: string
}
