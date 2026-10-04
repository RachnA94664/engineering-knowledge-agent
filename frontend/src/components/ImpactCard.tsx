import type { ImpactReport } from '../api/types'
import { formatTime, humanize } from '../lib/format'
import { Badge } from './Badge'

/** The automatic impact analysis of a confirmed change. Written by rules, never by the AI. */
export function ImpactCard({ report }: { report: ImpactReport }) {
  return (
    <section className="impact" aria-label={`Impact of the last change to ${report.requirement_id}`}>
      <header className="impact-head">
        <h4>
          Impact on {report.requirement_id} <Badge value={report.level} label={`${report.level} impact`} />
        </h4>
        <span className="muted">
          change #{report.change_id} · {formatTime(report.created_at)}
        </span>
      </header>
      <p className="impact-summary">{report.summary}</p>

      {report.tests_to_reset.length > 0 && (
        <div className="impact-section">
          <h5>Test cases reset</h5>
          <ul className="plain-list">
            {report.tests_to_reset.map((test) => (
              <li key={test.id}>
                <strong>{test.id}</strong> {test.title}{' '}
                <Badge value={test.old_status} /> → <Badge value={test.new_status} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.tests_failing.length > 0 && (
        <div className="impact-section">
          <h5>Already failing or blocked</h5>
          <ul className="plain-list">
            {report.tests_failing.map((test) => (
              <li key={test.id}>
                <strong>{test.id}</strong> {test.title} <Badge value={test.status} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.risks_to_flag.length > 0 && (
        <div className="impact-section">
          <h5>Risks flagged for review</h5>
          <ul className="plain-list">
            {report.risks_to_flag.map((risk) => (
              <li key={risk.id}>
                <strong>{risk.id}</strong> {risk.title} <Badge value={risk.level} /> (score {risk.score})
                {risk.already_flagged && <span className="muted"> · was already flagged</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.warnings.length > 0 && (
        <div className="impact-section">
          <h5>Warnings</h5>
          <ul className="plain-list">
            {report.warnings.map((warning) => (
              <li key={warning}>⚠ {humanize(warning)}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
