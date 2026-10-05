import type { Priority, RequirementStatus } from '../api/types'

/**
 * Which status a requirement may move to next. This mirrors backend/app/domain/transitions.py
 * ONLY so the form can offer sensible choices. The server is always the authority: if this
 * list ever drifts, the server still rejects an invalid move and we show its message.
 */
export const ALLOWED_TRANSITIONS: Record<RequirementStatus, RequirementStatus[]> = {
  draft: ['approved', 'obsolete'],
  approved: ['implemented', 'obsolete'],
  implemented: ['verified', 'obsolete'],
  verified: ['obsolete'],
  obsolete: [],
}

export const PRIORITIES: Priority[] = ['low', 'medium', 'high', 'critical']

export const REQUIREMENT_STATUSES: RequirementStatus[] = [
  'draft',
  'approved',
  'implemented',
  'verified',
  'obsolete',
]

export function nextStatuses(current: RequirementStatus): RequirementStatus[] {
  return ALLOWED_TRANSITIONS[current] ?? []
}
