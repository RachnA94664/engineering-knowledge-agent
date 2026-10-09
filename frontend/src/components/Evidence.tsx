import type { ToolCall } from '../api/types'
import { formatValue } from '../lib/format'

/** Fields that are long text: shown only when the record is opened. */
const LONG_FIELDS = new Set(['description', 'steps', 'expected_result', 'summary'])
const SHORT_FIELD_LIMIT = 7

function isScalar(value: unknown): boolean {
  return value === null || ['string', 'number', 'boolean'].includes(typeof value)
}

/** The database records an answer is based on: the evidence the user can check it against. */
export function RecordList({ records }: { records: Record<string, unknown>[] }) {
  if (records.length === 0) return null
  return (
    <details className="evidence">
      <summary>
        Records behind this answer <span className="count">{records.length}</span>
      </summary>
      <ul className="records">
        {records.map((record, index) => {
          const title = record.title ?? record.summary ?? record.status
          const fields = Object.entries(record).filter(
            ([key, value]) =>
              key !== 'id' && key !== 'title' && !LONG_FIELDS.has(key) && isScalar(value),
          )
          return (
            <li key={`${String(record.id)}-${index}`}>
              <div className="record-head">
                <strong>{formatValue(record.id)}</strong>
                {title !== undefined && <span> {formatValue(title)}</span>}
              </div>
              <dl className="chips">
                {fields.slice(0, SHORT_FIELD_LIMIT).map(([key, value]) => (
                  <div key={key} className="chip">
                    <dt>{key}</dt>
                    <dd>{formatValue(value)}</dd>
                  </div>
                ))}
              </dl>
            </li>
          )
        })}
      </ul>
    </details>
  )
}

/** Which tools the AI used, with their arguments: how the answer was found. */
export function ToolTrace({ calls }: { calls: ToolCall[] }) {
  if (calls.length === 0) return null
  return (
    <details className="evidence">
      <summary>
        Tools used <span className="count">{calls.length}</span>
      </summary>
      <ol className="trace">
        {calls.map((call, index) => (
          <li key={index} className={call.ok ? '' : 'trace-failed'}>
            <code>
              {call.name}({Object.keys(call.arguments).length ? JSON.stringify(call.arguments) : ''})
            </code>{' '}
            {call.ok ? <span className="ok-mark">✓</span> : <span className="fail-mark">✗ {call.error}</span>}
          </li>
        ))}
      </ol>
    </details>
  )
}
