import { useMemo, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type { Priority, Requirement, RequirementStatus } from '../api/types'
import { Badge } from '../components/Badge'
import { EmptyState, ErrorNotice, Spinner } from '../components/Feedback'
import { ImpactCard } from '../components/ImpactCard'
import { Stats } from '../components/Stats'
import { useApp } from '../context'
import { useAsync } from '../hooks/useAsync'
import { formatTime, humanize } from '../lib/format'
import { nextStatuses, PRIORITIES, REQUIREMENT_STATUSES } from '../lib/transitions'

// ---------- propose a change ----------

function ProposeForm({ requirement }: { requirement: Requirement }) {
  const { actor, notify, bump } = useApp()
  const [status, setStatus] = useState<RequirementStatus | ''>('')
  const [priority, setPriority] = useState<Priority>(requirement.priority)
  const [title, setTitle] = useState(requirement.title)
  const [description, setDescription] = useState(requirement.description)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const choices = nextStatuses(requirement.status)
  const patch: Record<string, string> = {}
  if (status) patch.status = status
  if (priority !== requirement.priority) patch.priority = priority
  if (title.trim() !== requirement.title) patch.title = title.trim()
  if (description !== requirement.description) patch.description = description
  const hasChange = Object.keys(patch).length > 0
  const name = actor.trim()

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!hasChange || !name) return
    setSaving(true)
    setError(null)
    try {
      const result = await api.proposeChange(requirement.id, patch, name)
      notify('success', `Change #${result.change.id} proposed. Review it on the Pending page.`)
      bump()
      setStatus('')
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Unexpected error.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      <h4>Propose a change</h4>
      <p className="muted">
        This only <em>proposes</em>. Nothing changes until you confirm it on the Pending page.
      </p>
      <div className="form-grid">
        <label>
          Status
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as RequirementStatus | '')}
            disabled={choices.length === 0}
          >
            <option value="">Keep {humanize(requirement.status)}</option>
            {choices.map((option) => (
              <option key={option} value={option}>
                Move to {humanize(option)}
              </option>
            ))}
          </select>
          {choices.length === 0 && <span className="muted">Obsolete is final.</span>}
        </label>
        <label>
          Priority
          <select value={priority} onChange={(event) => setPriority(event.target.value as Priority)}>
            {PRIORITIES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label>
        Title
        <input value={title} maxLength={200} onChange={(event) => setTitle(event.target.value)} />
      </label>
      <label>
        Description
        <textarea rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
      </label>
      {error && (
        <div className="notice notice-error" role="alert">
          {error}
        </div>
      )}
      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={!hasChange || !name || saving}>
          {saving ? 'Proposing…' : 'Propose change'}
        </button>
        {!name && <span className="muted">Enter your name in the top bar first.</span>}
        {name && !hasChange && <span className="muted">Change a field to propose it.</span>}
      </div>
    </form>
  )
}

// ---------- one requirement ----------

function RequirementDetail({ requirement }: { requirement: Requirement }) {
  const { refreshKey } = useApp()
  const tests = useAsync(() => api.getTestCases(requirement.id), [requirement.id, refreshKey])
  const impact = useAsync(() => api.getImpact(requirement.id), [requirement.id, refreshKey])

  return (
    <aside className="detail" aria-label={`Details of ${requirement.id}`}>
      <header>
        <h3>
          {requirement.id} <Badge value={requirement.status} /> <Badge value={requirement.priority} />
        </h3>
        <p className="detail-title">{requirement.title}</p>
        <p>{requirement.description}</p>
        <p className="muted">
          version {requirement.version} · updated {formatTime(requirement.updated_at)}
        </p>
      </header>

      <section>
        <h4>Test cases</h4>
        {tests.loading && !tests.data && <Spinner />}
        {tests.error && <ErrorNotice error={tests.error} onRetry={tests.reload} />}
        {tests.data && tests.data.length === 0 && <EmptyState>No test cases yet.</EmptyState>}
        {tests.data && tests.data.length > 0 && (
          <ul className="plain-list">
            {tests.data.map((test) => (
              <li key={test.id}>
                <strong>{test.id}</strong> {test.title} <Badge value={test.status} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h4>Latest impact</h4>
        {impact.loading && impact.data === undefined && <Spinner />}
        {impact.error && <ErrorNotice error={impact.error} onRetry={impact.reload} />}
        {impact.data === null && (
          <EmptyState>No confirmed change yet, so there is no impact report.</EmptyState>
        )}
        {impact.data && <ImpactCard report={impact.data} />}
      </section>

      <ProposeForm key={`${requirement.id}-${requirement.version}`} requirement={requirement} />
    </aside>
  )
}

// ---------- the list ----------

const count = (items: Requirement[], status: RequirementStatus) =>
  items.filter((item) => item.status === status).length

export function RequirementsPage() {
  const { refreshKey } = useApp()
  const requirements = useAsync(api.listRequirements, [refreshKey])
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<RequirementStatus | ''>('')
  const [priority, setPriority] = useState<Priority | ''>('')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return (requirements.data ?? []).filter(
      (item) =>
        (!status || item.status === status) &&
        (!priority || item.priority === priority) &&
        (!needle || `${item.id} ${item.title}`.toLowerCase().includes(needle)),
    )
  }, [requirements.data, search, status, priority])

  const selected = requirements.data?.find((item) => item.id === selectedId) ?? null

  return (
    <section className="page" aria-labelledby="req-title">
      <header className="page-header">
        <h2 id="req-title">Requirements</h2>
        <p className="lead">What the product must do, with its test cases and the impact of each change.</p>
      </header>
      {requirements.data && (
        <Stats
          items={[
            { label: 'Total', value: requirements.data.length },
            { label: 'Verified', value: count(requirements.data, 'verified'), tone: 'green' },
            {
              label: 'In progress',
              value: count(requirements.data, 'approved') + count(requirements.data, 'implemented'),
              tone: 'blue',
            },
            { label: 'Draft', value: count(requirements.data, 'draft'), tone: 'amber' },
          ]}
        />
      )}
      <div className="toolbar">
        <label>
          Search
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="REQ-009 or a word from the title"
          />
        </label>
        <label>
          Status
          <select value={status} onChange={(event) => setStatus(event.target.value as RequirementStatus | '')}>
            <option value="">All</option>
            {REQUIREMENT_STATUSES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label>
          Priority
          <select value={priority} onChange={(event) => setPriority(event.target.value as Priority | '')}>
            <option value="">All</option>
            {PRIORITIES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <span className="muted toolbar-count">
          {requirements.data ? `${visible.length} of ${requirements.data.length}` : ''}
        </span>
      </div>

      {requirements.loading && !requirements.data && <Spinner />}
      {requirements.error && <ErrorNotice error={requirements.error} onRetry={requirements.reload} />}

      <div className={selected ? 'split split-open' : 'split'}>
        <div className="table-wrap">
          {requirements.data && visible.length === 0 && <EmptyState>No requirement matches.</EmptyState>}
          {visible.length > 0 && (
            <table className="data">
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">Title</th>
                  <th scope="col">Priority</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((item) => (
                  <tr key={item.id} className={item.id === selectedId ? 'row-selected' : undefined}>
                    <td>
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => setSelectedId(item.id)}
                        aria-pressed={item.id === selectedId}
                      >
                        {item.id}
                      </button>
                    </td>
                    <td>{item.title}</td>
                    <td>
                      <Badge value={item.priority} />
                    </td>
                    <td>
                      <Badge value={item.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        {selected && <RequirementDetail key={selected.id} requirement={selected} />}
      </div>
    </section>
  )
}
