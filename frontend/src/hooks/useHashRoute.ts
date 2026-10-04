import { useEffect, useState } from 'react'

export const ROUTES = ['chat', 'requirements', 'risks', 'pending', 'audit'] as const
export type Route = (typeof ROUTES)[number]

function readRoute(): Route {
  const name = window.location.hash.replace(/^#\/?/, '').split(/[/?]/)[0]
  return (ROUTES as readonly string[]).includes(name) ? (name as Route) : 'chat'
}

/** A tiny router: the page is the part after "#/" in the address, e.g. #/pending. */
export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(readRoute)
  useEffect(() => {
    const onChange = () => setRoute(readRoute())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}
