import { useEffect, useState } from 'react'
import { api } from './api/client'
import type { Health } from './api/types'
import { Icon, type IconName } from './components/Icon'
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

const NAV: Record<Route, { label: string; icon: IconName }> = {
  chat: { label: 'Ask', icon: 'chat' },
  requirements: { label: 'Requirements', icon: 'list' },
  risks: { label: 'Risks', icon: 'shield' },
  pending: { label: 'Pending', icon: 'inbox' },
  audit: { label: 'Audit log', icon: 'history' },
}

type HealthState = Health | 'unreachable' | null

/** Null while unknown. "unreachable" when the server cannot be contacted at all. */
function useHealth(): HealthState {
  const [health, setHealth] = useState<HealthState>(null)
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

function HealthPill({ health }: { health: HealthState }) {
  if (health === null) return <span className="pill">Checking…</span>
  if (health === 'unreachable') return <span className="pill pill-bad">Backend offline</span>
  if (health.status !== 'ok') return <span className="pill pill-warn">Needs attention</span>
  return <span className="pill pill-ok">Backend connected</span>
}

function HealthBanner({ health }: { health: HealthState }) {
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
            <Icon name="x" size={14} />
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
  const health = useHealth()
  const pendingCount = pending.data?.length ?? 0

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <Icon name="spark" size={18} />
          </span>
          <div>
            <h1>Engineering Knowledge Agent</h1>
            <span className="brand-sub">Requirements · Tests · Risks</span>
          </div>
        </div>

        <nav aria-label="Main">
          {ROUTES.map((name) => (
            <a
              key={name}
              href={`#/${name}`}
              className={name === route ? 'nav-link nav-active' : 'nav-link'}
              aria-current={name === route ? 'page' : undefined}
            >
              <Icon name={NAV[name].icon} />
              <span className="nav-label">{NAV[name].label}</span>
              {name === 'pending' && pendingCount > 0 && (
                <span className="nav-count" aria-label={`${pendingCount} waiting`}>
                  {pendingCount}
                </span>
              )}
            </a>
          ))}
        </nav>

        <div className="sidebar-foot">
          <label className="actor">
            Your name
            <input
              value={actor}
              maxLength={ACTOR_MAX_LENGTH}
              onChange={(event) => setActor(event.target.value)}
              placeholder="used in the audit log"
            />
          </label>
          <HealthPill health={health} />
        </div>
      </aside>

      <div className="content">
        <HealthBanner health={health} />
        <main>
          {route === 'chat' && <ChatPage />}
          {route === 'requirements' && <RequirementsPage />}
          {route === 'risks' && <RisksPage />}
          {route === 'pending' && <PendingPage />}
          {route === 'audit' && <AuditPage />}
        </main>
      </div>
      <Toasts />
    </div>
  )
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  )
}
