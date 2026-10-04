import { useEffect, useState } from 'react'
import { api } from './api/client'
import type { Health } from './api/types'
import { AppProvider, useApp } from './context'
import { useAsync } from './hooks/useAsync'
import { ROUTES, useHashRoute, type Route } from './hooks/useHashRoute'
import { ACTOR_MAX_LENGTH } from './lib/format'
import { AuditPage } from './pages/AuditPage'
import { ChatPage } from './pages/ChatPage'
import { PendingPage } from './pages/PendingPage'
import { RequirementsPage } from './pages/RequirementsPage'
import { RisksPage } from './pages/RisksPage'

const HEALTH_POLL_MS = 30_000

const LABELS: Record<Route, string> = {
  chat: 'Ask',
  requirements: 'Requirements',
  risks: 'Risks',
  pending: 'Pending',
  audit: 'Audit log',
}

/** Null while unknown. "unreachable" when the server cannot be contacted at all. */
function useHealth(): Health | 'unreachable' | null {
  const [health, setHealth] = useState<Health | 'unreachable' | null>(null)
  useEffect(() => {
    let cancelled = false
    const check = () =>
      api.health().then(
        (value) => !cancelled && setHealth(value),
        () => !cancelled && setHealth('unreachable'),
      )
    void check()
    const timer = window.setInterval(check, HEALTH_POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])
  return health
}

function HealthBanner() {
  const health = useHealth()
  if (health === null) return null
  if (health === 'unreachable') {
    return (
      <div className="banner banner-error" role="alert">
        Cannot reach the backend. Start it, or check the API address.
      </div>
    )
  }
  if (health.status !== 'ok') {
    return (
      <div className="banner banner-error" role="alert">
        The backend is running but not healthy: {health.database}
      </div>
    )
  }
  return null
}

function Toasts() {
  const { toasts, dismiss } = useApp()
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.kind}`}>
          <span>{toast.text}</span>
          <button type="button" className="toast-close" aria-label="Dismiss" onClick={() => dismiss(toast.id)}>
            ×
          </button>
        </div>
      ))}
    </div>
  )
}

function Shell() {
  const route = useHashRoute()
  const { actor, setActor, refreshKey } = useApp()
  const pending = useAsync(api.listPending, [refreshKey])
  const pendingCount = pending.data?.length ?? 0

  return (
    <>
      <header className="topbar">
        <h1>Engineering Knowledge Agent</h1>
        <nav aria-label="Main">
          {ROUTES.map((name) => (
            <a
              key={name}
              href={`#/${name}`}
              className={name === route ? 'nav-link nav-active' : 'nav-link'}
              aria-current={name === route ? 'page' : undefined}
            >
              {LABELS[name]}
              {name === 'pending' && pendingCount > 0 && (
                <span className="nav-count" aria-label={`${pendingCount} waiting`}>
                  {pendingCount}
                </span>
              )}
            </a>
          ))}
        </nav>
        <label className="actor">
          Your name
          <input
            value={actor}
            maxLength={ACTOR_MAX_LENGTH}
            onChange={(event) => setActor(event.target.value)}
            placeholder="used in the audit log"
          />
        </label>
      </header>
      <HealthBanner />
      <main>
        {route === 'chat' && <ChatPage />}
        {route === 'requirements' && <RequirementsPage />}
        {route === 'risks' && <RisksPage />}
        {route === 'pending' && <PendingPage />}
        {route === 'audit' && <AuditPage />}
      </main>
      <Toasts />
    </>
  )
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  )
}
