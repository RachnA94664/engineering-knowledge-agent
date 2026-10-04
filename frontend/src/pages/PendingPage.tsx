import { useState } from 'react'
import { api } from '../api/client'
import type { Change, Preview, Requirement } from '../api/types'
import { EmptyState, ErrorNotice, Spinner } from '../components/Feedback'
import { ProposalCard } from '../components/ProposalCard'
import { useApp } from '../context'
import { useAsync } from '../hooks/useAsync'

/** Show each proposed field next to the value it has right now. */
function buildPreview(change: Change, requirements: Requirement[]): Preview {
  const current = requirements.find((item) => item.id === change.entity_id) as
    | Record<string, unknown>
    | undefined
  const preview: Preview = {}
  for (const [field, value] of Object.entries(change.patch)) {
    preview[field] = { old: current?.[field] ?? null, new: value }
  }
  return preview
}

interface Kept {
  change: Change
  preview: Preview
}

export function PendingPage() {
  const { refreshKey } = useApp()
  const pending = useAsync(api.listPending, [refreshKey])
  const requirements = useAsync(api.listRequirements, [refreshKey])
  // A card that was just confirmed/rejected is no longer "pending", so the list would drop it
  // together with its result (the impact report). We keep it on screen until Refresh is pressed.
  const [kept, setKept] = useState<Map<number, Kept>>(new Map())

  const error = pending.error ?? requirements.error
  const ready = pending.data && requirements.data

  function reload() {
    setKept(new Map())
    pending.reload()
    requirements.reload()
  }

  const cards: Kept[] = []
  if (ready) {
    for (const change of pending.data!) {
      cards.push(kept.get(change.id) ?? { change, preview: buildPreview(change, requirements.data!) })
    }
    for (const item of kept.values()) {
      if (!cards.some((card) => card.change.id === item.change.id)) cards.push(item)
    }
    cards.sort((a, b) => a.change.id - b.change.id)
  }

  return (
    <section className="page" aria-labelledby="pending-title">
      <div className="page-head">
        <h2 id="pending-title">Pending changes</h2>
        <button type="button" className="btn btn-small" onClick={reload}>
          Refresh
        </button>
      </div>
      <p className="lead">
        Proposals wait here until a person confirms or rejects them. Nothing is applied before that.
      </p>

      {!ready && !error && <Spinner />}
      {error && <ErrorNotice error={error} onRetry={reload} />}
      {ready && cards.length === 0 && <EmptyState>Nothing is waiting for review.</EmptyState>}
      <div className="proposal-list">
        {cards.map(({ change, preview }) => (
          <ProposalCard
            key={change.id}
            change={change}
            preview={preview}
            onResolved={() =>
              setKept((all) => new Map(all).set(change.id, { change, preview }))
            }
          />
        ))}
      </div>
    </section>
  )
}
