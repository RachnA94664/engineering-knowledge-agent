export interface Stat {
  label: string
  value: number | string
  tone?: 'neutral' | 'green' | 'amber' | 'red' | 'blue'
}

/** A row of headline numbers: the first thing a reviewer wants to know about a list. */
export function Stats({ items }: { items: Stat[] }) {
  return (
    <div className="stats">
      {items.map((item) => (
        <div key={item.label} className={`stat stat-${item.tone ?? 'neutral'}`}>
          <span className="stat-value">{item.value}</span>
          <span className="stat-label">{item.label}</span>
        </div>
      ))}
    </div>
  )
}
