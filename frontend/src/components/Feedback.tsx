import type { ReactNode } from 'react'
import type { ApiError } from '../api/client'

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <span className="spinner-row" role="status">
      <span className="spinner" aria-hidden="true" />
      {label}
    </span>
  )
}

export function ErrorNotice({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div className="notice notice-error" role="alert">
      <strong>Something went wrong.</strong> {error.message}
      {onRetry && (
        <button type="button" className="btn btn-small" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>
}
