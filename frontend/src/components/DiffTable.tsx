import type { Preview } from '../api/types'
import { formatValue, humanize } from '../lib/format'

/** What a change would do: each field, its current value and the proposed value. */
export function DiffTable({ preview }: { preview: Preview }) {
  const rows = Object.entries(preview)
  return (
    <table className="diff">
      <thead>
        <tr>
          <th scope="col">Field</th>
          <th scope="col">Now</th>
          <th scope="col">Proposed</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([field, change]) => (
          <tr key={field}>
            <th scope="row">{humanize(field)}</th>
            <td className="diff-old">{formatValue(change.old)}</td>
            <td className="diff-new">{formatValue(change.new)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
