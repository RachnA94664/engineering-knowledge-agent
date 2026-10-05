import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { ACTOR_MAX_LENGTH } from './lib/format'

export interface Toast {
  id: number
  kind: 'success' | 'error' | 'info'
  text: string
}

interface AppContextValue {
  /** The name written into the audit log for anything this person does. */
  actor: string
  setActor: (name: string) => void
  /** Increases after every change, so lists everywhere reload. */
  refreshKey: number
  bump: () => void
  toasts: Toast[]
  notify: (kind: Toast['kind'], text: string) => void
  dismiss: (id: number) => void
}

const ACTOR_STORAGE_KEY = 'eka.actor'
const TOAST_SECONDS = 7

const AppContext = createContext<AppContextValue | null>(null)

function readStoredActor(): string {
  try {
    return window.localStorage.getItem(ACTOR_STORAGE_KEY) ?? ''
  } catch {
    return '' // storage can be blocked (private windows): the app still works
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [actor, setActorState] = useState<string>(readStoredActor)
  const [refreshKey, setRefreshKey] = useState(0)
  const [toasts, setToasts] = useState<Toast[]>([])

  const setActor = useCallback((name: string) => {
    const clean = name.slice(0, ACTOR_MAX_LENGTH)
    setActorState(clean)
    try {
      window.localStorage.setItem(ACTOR_STORAGE_KEY, clean)
    } catch {
      /* ignore: remembering the name is a convenience only */
    }
  }, [])

  const bump = useCallback(() => setRefreshKey((value) => value + 1), [])
  const dismiss = useCallback(
    (id: number) => setToasts((all) => all.filter((toast) => toast.id !== id)),
    [],
  )
  const notify = useCallback(
    (kind: Toast['kind'], text: string) => {
      const id = Date.now() + Math.random()
      setToasts((all) => [...all, { id, kind, text }])
      window.setTimeout(() => dismiss(id), TOAST_SECONDS * 1000)
    },
    [dismiss],
  )

  const value = useMemo(
    () => ({ actor, setActor, refreshKey, bump, toasts, notify, dismiss }),
    [actor, setActor, refreshKey, bump, toasts, notify, dismiss],
  )
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp(): AppContextValue {
  const value = useContext(AppContext)
  if (value === null) throw new Error('useApp must be used inside <AppProvider>')
  return value
}
