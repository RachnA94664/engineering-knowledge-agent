import { humanize } from '../lib/format'

type Tone = 'neutral' | 'blue' | 'green' | 'amber' | 'red' | 'violet'

/** One colour per meaning, so the same word always looks the same everywhere. */
const TONES: Record<string, Tone> = {
  // requirement status
  draft: 'neutral',
  approved: 'blue',
  implemented: 'violet',
  verified: 'green',
  obsolete: 'neutral',
  // test status
  pass: 'green',
  fail: 'red',
  not_run: 'neutral',
  blocked: 'amber',
  // risk level / priority
  low: 'green',
  medium: 'amber',
  high: 'red',
  critical: 'red',
  // risk status
  open: 'amber',
  mitigated: 'green',
  accepted: 'blue',
  closed: 'neutral',
  // change status
  pending: 'amber',
  applied: 'green',
  rejected: 'neutral',
  expired: 'neutral',
  // who did it
  ui: 'blue',
  agent: 'violet',
  system: 'amber',
  // chat intent
  query: 'blue',
  update: 'violet',
  analysis: 'violet',
  out_of_scope: 'neutral',
  refused: 'red',
}

export function Badge({ value, label }: { value: string; label?: string }) {
  const tone = TONES[value] ?? 'neutral'
  return <span className={`badge badge-${tone}`}>{label ?? humanize(value)}</span>
}
