import { useEffect, useState } from 'react'

export type Route =
  | { name: 'queue' }
  | { name: 'founder'; id: string }
  | { name: 'pipeline' }

/** Parse the location hash into a Route. Unknown paths fall back to the queue. */
export function parseHash(hash: string): Route {
  const clean = hash.replace(/^#\/?/, '')
  if (clean.startsWith('founders/')) {
    return { name: 'founder', id: decodeURIComponent(clean.slice('founders/'.length)) }
  }
  if (clean.startsWith('pipeline')) return { name: 'pipeline' }
  return { name: 'queue' }
}

/** Navigate by setting the hash; `useRoute` picks up the change. */
export function navigate(path: string) {
  window.location.hash = path
}

/** Current route, kept in sync with `hashchange`. Hash routing keeps the app
 *  a static bundle with no server-side route configuration. */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

/** The signed-in reviewer. Every human mutation is attributed to them. */
const ACTOR_KEY = 'fe.actor'

/**
 * The acting reviewer, from localStorage. Sent as `actor` on every human
 * mutation and recorded in the audit trail. This is attribution ON TRUST, not
 * authentication — there is no auth and no RBAC in this MVP.
 */
export function getActor(): string {
  return window.localStorage.getItem(ACTOR_KEY) || 'piyush'
}

/** Change the acting reviewer. */
export function setActor(name: string) {
  window.localStorage.setItem(ACTOR_KEY, name)
}
