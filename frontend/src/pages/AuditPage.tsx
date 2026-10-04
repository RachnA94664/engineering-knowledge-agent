import { useState } from 'react'
import { api } from '../api/client'
import { Badge } from '../components/Badge'
import { EmptyState, ErrorNotice, Spinner } from '../components/Feedback'
import { useApp } from '../context'
import { useAsync } from '../hooks/useAsync'
import { formatTime, formatValue, humanize } from '../lib/format'

const LIMITS = [25, 50, 100, 200]

export function AuditPage() {
  const { refreshKey } = useApp()
  const [entityId, setEntityId] = useState('')
  const [limit, setLimit] = useState(50)
  const log = useAsync(
    () => api.getAuditLog({ limit, entityId: entityId.trim().toUpperCase() }),
    [limit, entityId, refreshKey],
  )

  return (
    <section className="page" aria-labelledby="audit-title">
      <header className="page-header">
        <h2 id="audit-title">Audit log</h2>
        <p className="lead">
          Every change is recorded: who did it, when, and what it was before and after. The log
          cannot be edited or deleted.
        </p>
      </header>
      <div className="toolbar">
        <label>
          Record
          <input
            value={entityId}
            onChange={(event) => setEntityId(event.target.value)}
            placeholder="e.g. REQ-009"
          />
        </label>
        <label>
          Show
          <select value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
            {LIMITS.map((option) => (
              <option key={option} value={option}>
                last {option}
              </option>
            ))}
          </select>
        </label>
      </div>

      {log.loading && !log.data && <Spinner />}
      {log.error && <ErrorNotice error={log.error} onRetry={log.reload} />}
      {log.data && log.data.length === 0 && <EmptyState>No audit entries match.</EmptyState>}
      {log.data && log.data.length > 0 && (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Who</th>
                <th scope="col">Record</th>
                <th scope="col">Action</th>
                <th scope="col">Before → after</th>
              </tr>
            </thead>
            <tbody>
              {log.data.map((entry) => (
                <tr key={entry.id}>
                  <td>{formatTime(entry.ts)}</td>
                  <td>
                    {entry.actor} <Badge value={entry.source} />
                  </td>
                  <td>{entry.entity_id}</td>
                  <td>{humanize(entry.action)}</td>
                  <td>
                    <code>{formatValue(entry.old_value)}</code> → <code>{formatValue(entry.new_value)}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
