import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'

interface Settled<T> {
  key: string
  data?: T
  error?: ApiError
}

export interface AsyncState<T> {
  data: T | undefined
  error: ApiError | undefined
  /** True until the request for the CURRENT inputs has finished. */
  loading: boolean
  reload: () => void
}

/**
 * Load something from the API.
 *
 * - Reloads when `deps` change or `reload()` is called.
 * - `loading` is DERIVED (is the settled result for the current inputs?), so we never have to
 *   call setState synchronously inside the effect.
 * - A late answer for old inputs is ignored.
 */
export function useAsync<T>(load: () => Promise<T>, deps: readonly unknown[]): AsyncState<T> {
  const [tick, setTick] = useState(0)
  const [settled, setSettled] = useState<Settled<T> | null>(null)
  const loadRef = useRef(load)
  const key = `${tick}|${JSON.stringify(deps)}`

  useEffect(() => {
    loadRef.current = load
  })

  useEffect(() => {
    let cancelled = false
    loadRef.current().then(
      (data) => {
        if (!cancelled) setSettled({ key, data })
      },
      (error: unknown) => {
        if (cancelled) return
        const apiError =
          error instanceof ApiError
            ? error
            : new ApiError(0, 'unexpected', error instanceof Error ? error.message : String(error))
        setSettled({ key, error: apiError })
      },
    )
    return () => {
      cancelled = true
    }
  }, [key])

  const reload = useCallback(() => setTick((value) => value + 1), [])
  const current = settled?.key === key ? settled : null
  return {
    data: current?.data ?? settled?.data, // keep showing the previous data while reloading
    error: current?.error,
    loading: current === null,
    reload,
  }
}
