import { useState } from 'react'
import { api, ApiError } from '../api/client'
import type { Change, ImpactReport, Preview } from '../api/types'
import { useApp } from '../context'
import { formatTime } from '../lib/format'
import { Badge } from './Badge'
import { DiffTable } from './DiffTable'
import { ImpactCard } from './ImpactCard'

export interface Outcome {
  change: Change
  kind: 'applied' | 'rejected' | 'expired'
  impact?: ImpactReport | null
  message?: string
}

type Phase =
  | { name: 'idle' }
  | { name: 'working' }
  | { name: 'applied'; impact: ImpactReport | null }
  | { name: 'rejected' }
  | { name: 'failed'; message: string; expired: boolean }

interface Props {
  change: Change
  preview: Preview
  onResolved?: (outcome: Outcome) => void
}

/**
 * A proposed change waiting for a PERSON to decide. Nothing is applied until Confirm is
 * pressed. Confirming runs the automatic impact analysis, shown right here.
 */
export function ProposalCard({ change, preview, onResolved }: Props) {
  const { actor, notify, bump } = useApp()
  const [phase, setPhase] = useState<Phase>({ name: 'idle' })
  const name = actor.trim()
  const canAct = name.length > 0 && phase.name === 'idle'

  async function confirm() {
    setPhase({ name: 'working' })
    try {
      const result = await api.confirmChange(change.id, name)
      setPhase({ name: 'applied', impact: result.impact })
      notify('success', `Change #${change.id} applied to ${change.entity_id}.`)
      bump()
      onResolved?.({ change: result.change, kind: 'applied', impact: result.impact })
    } catch (error) {
      const message = error instanceof ApiError ? error.message : 'Unexpected error.'
      const expired = error instanceof ApiError && error.status === 409
      setPhase({ name: 'failed', message, expired })
      if (expired) onResolved?.({ change, kind: 'expired', message })
    }
  }

  async function reject() {
    setPhase({ name: 'working' })
    try {
      const result = await api.rejectChange(change.id, name)
      setPhase({ name: 'rejected' })
      notify('info', `Change #${change.id} rejected. Nothing was changed.`)
      bump()
      onResolved?.({ change: result.change, kind: 'rejected' })
    } catch (error) {
      const message = error instanceof ApiError ? error.message : 'Unexpected error.'
      setPhase({ name: 'failed', message, expired: false })
    }
  }

  return (
    <article className="proposal" aria-label={`Proposed change ${change.id}`}>
      <header className="proposal-head">
        <h4>
          Proposed change #{change.id} for <strong>{change.entity_id}</strong>
        </h4>
        <Badge
          value={phase.name === 'applied' ? 'applied' : phase.name === 'rejected' ? 'rejected' : 'pending'}
        />
      </header>
      <p className="muted">
        Proposed by {change.proposed_by} · {formatTime(change.created_at)}
      </p>
      <DiffTable preview={preview} />

      {(phase.name === 'idle' || phase.name === 'working') && (
        <div className="proposal-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={confirm}
            disabled={!canAct}
            aria-busy={phase.name === 'working'}
          >
            {phase.name === 'working' ? 'Working…' : 'Confirm change'}
          </button>
          <button type="button" className="btn" onClick={reject} disabled={!canAct}>
            Reject
          </button>
          {name.length === 0 && (
            <span className="muted">Enter your name in the top bar to confirm or reject.</span>
          )}
        </div>
      )}

      {phase.name === 'applied' && (
        <>
          <div className="notice notice-success" role="status">
            Applied. Nothing else was needed: the impact analysis ran automatically.
          </div>
          {phase.impact && <ImpactCard report={phase.impact} />}
        </>
      )}
      {phase.name === 'rejected' && (
        <div className="notice" role="status">
          Rejected. Nothing was changed.
        </div>
      )}
      {phase.name === 'failed' && (
        <div className="notice notice-error" role="alert">
          {phase.message}
          {phase.expired && ' This proposal can no longer be applied: propose it again.'}
        </div>
      )}
    </article>
  )
}
