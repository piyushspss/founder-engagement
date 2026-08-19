// Loading / empty / error. Plain, readable, no design heroics.

import { ApiError } from '../api'

/** Loading placeholder. */
export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 p-6 text-sm text-slate-500">
      <span aria-hidden
            className="h-3 w-3 animate-pulse rounded-full bg-slate-400" />
      {label}
    </div>
  )
}

/** Empty-result placeholder — distinct from an error, which is a failure. */
export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center">
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {hint && <p className="mt-1 text-sm text-slate-500">{hint}</p>}
    </div>
  )
}

/** Error surface. Shows the API's own message so a rejected human action
 *  (e.g. a 409 illegal transition) explains itself rather than failing silently. */
export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const api = error instanceof ApiError ? error : null
  const status = api?.status ?? 0
  const title = status === 404 ? 'Not found'
    : status === 409 ? 'Not an allowed transition'
      : status === 422 ? 'The request was rejected'
        : status === 0 ? 'Cannot reach the API'
          : `Request failed (HTTP ${status})`
  return (
    <div role="alert"
         className="rounded-lg border border-rose-300 bg-rose-50 p-4 text-sm text-rose-900">
      <p className="font-semibold">{title}</p>
      <p className="mt-1 break-words">{api?.detail ?? String(error)}</p>
      {api && api.errors.length > 1 && (
        <ul className="mt-2 list-disc pl-5">
          {api.errors.map((e) => <li key={e} className="break-words">{e}</li>)}
        </ul>
      )}
      {onRetry && (
        <button type="button" onClick={onRetry}
                className="mt-3 rounded border border-rose-400 bg-white px-2.5 py-1 text-xs
                           font-medium text-rose-800 hover:bg-rose-100">
          Try again
        </button>
      )}
    </div>
  )
}

/** Inline notice banner. */
export function Banner({ tone, children }:
  { tone: 'info' | 'warn' | 'ok'; children: React.ReactNode }) {
  const cls = tone === 'warn' ? 'border-amber-300 bg-amber-50 text-amber-900'
    : tone === 'ok' ? 'border-emerald-300 bg-emerald-50 text-emerald-900'
      : 'border-slate-300 bg-slate-50 text-slate-700'
  return (
    <div className={`rounded-md border px-3 py-2 text-sm ${cls}`}>{children}</div>
  )
}
