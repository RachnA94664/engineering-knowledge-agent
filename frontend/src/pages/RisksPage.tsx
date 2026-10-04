import { useState } from 'react'
import { api, ApiError } from '../api/client'
import type { Risk, RiskLevel } from '../api/types'
import { Badge } from '../components/Badge'
import { EmptyState, ErrorNotice, Spinner } from '../components/Feedback'
import { useApp } from '../context'
import { useAsync } from '../hooks/useAsync'

const LEVELS: RiskLevel[] = ['high', 'medium', 'low']

function RiskRow({ risk }: { risk: Risk }) {
  const { actor, notify, bump } = useApp()
  const [working, setWorking] = useState(false)
  const name = actor.trim()

  async function markReviewed() {
    setWorking(true)
    try {
      await api.markRiskReviewed(risk.id, name)
      notify('success', `${risk.id} marked as reviewed.`)
      bump()
    } catch (error) {
      notify('error', error instanceof ApiError ? error.message : 'Unexpected error.')
    } finally {
      setWorking(false)
    }
  }

  return (
    <tr>
      <td>{risk.id}</td>
      <td>
        {risk.title}
        {risk.needs_review && (
          <>
            {' '}
            <Badge value="pending" label="Needs review" />
          </>
        )}
      </td>
      <td>
        <Badge value={risk.level} /> <span className="muted">score {risk.score}</span>
      </td>
      <td>
        {risk.severity} × {risk.likelihood}
      </td>
      <td>
        {risk.needs_review && (
          <button
            type="button"
            className="btn btn-small"
            onClick={markReviewed}
            disabled={!name || working}
            title={name ? undefined : 'Enter your name in the top bar first'}
          >
            {working ? 'Saving…' : 'Mark reviewed'}
          </button>
        )}
      </td>
    </tr>
  )
}

export function RisksPage() {
  const { refreshKey } = useApp()
  const [level, setLevel] = useState<RiskLevel | ''>('')
  const [needsReview, setNeedsReview] = useState(false)
  const risks = useAsync(
    () => api.listRisks({ level, needsReview }),
    [level, needsReview, refreshKey],
  )

  return (
    <section className="page" aria-labelledby="risk-title">
      <h2 id="risk-title">Risks</h2>
      <p className="lead">
        A risk is flagged for review automatically when a change affects its requirement. Only a
        person can clear the flag.
      </p>
      <div className="toolbar">
        <label>
          Level
          <select value={level} onChange={(event) => setLevel(event.target.value as RiskLevel | '')}>
            <option value="">All</option>
            {LEVELS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={needsReview}
            onChange={(event) => setNeedsReview(event.target.checked)}
          />
          Only risks that need review
        </label>
      </div>

      {risks.loading && !risks.data && <Spinner />}
      {risks.error && <ErrorNotice error={risks.error} onRetry={risks.reload} />}
      {risks.data && risks.data.length === 0 && <EmptyState>No risks match.</EmptyState>}
      {risks.data && risks.data.length > 0 && (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th scope="col">ID</th>
                <th scope="col">Title</th>
                <th scope="col">Level</th>
                <th scope="col">Severity × likelihood</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {risks.data.map((risk) => (
                <RiskRow key={risk.id} risk={risk} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
