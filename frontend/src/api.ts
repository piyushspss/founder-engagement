// Thin API client. Every screen reads from here; nothing derives a machine
// dimension locally.

import type {
  AICheckResponse, AuditEvent, Dashboard, EffectiveConfig, FounderDetail,
  QueueResponse, Stage,
} from './types'

/** Vite proxies `/api` to the FastAPI process on :8000. */
const BASE = '/api'

/** An API failure. `status` 0 means the API could not be reached at all. */
export class ApiError extends Error {
  status: number
  detail: string
  errors: string[]
  constructor(status: number, detail: string, errors: string[] = []) {
    super(detail)
    this.status = status
    this.detail = detail
    this.errors = errors
  }
}

/** One API call. Normalises FastAPI's several error shapes into `ApiError`,
 *  and reports an unreachable API distinctly from a rejected request. */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { 'content-type': 'application/json' },
      ...init,
    })
  } catch {
    throw new ApiError(0, 'Could not reach the API. Is it running on :8000?')
  }
  const text = await response.text()
  const body = text ? JSON.parse(text) : null
  if (!response.ok) {
    const detail: string =
      body?.detail ??
      (Array.isArray(body?.errors) ? body.errors.join('; ') : null) ??
      (Array.isArray(body?.detail) ? body.detail.map((d: { msg: string }) => d.msg).join('; ')
        : null) ??
      `Request failed (HTTP ${response.status})`
    throw new ApiError(response.status, detail, body?.errors ?? [])
  }
  return body as T
}

export interface QueueFilters {
  attention?: string[]
  data_state?: string[]
  stage?: string[]
  owner?: string
  due?: boolean
  as_of?: string
  limit?: number
}

/** Serialise queue filters into a query string. Every filter is applied
 *  SERVER-side; the client never re-ranks or re-filters rows locally. */
export function queueQuery(filters: QueueFilters): string {
  const params = new URLSearchParams()
  filters.attention?.forEach((v) => params.append('attention', v))
  filters.data_state?.forEach((v) => params.append('data_state', v))
  filters.stage?.forEach((v) => params.append('stage', v))
  if (filters.owner !== undefined && filters.owner !== '') params.set('owner', filters.owner)
  if (filters.due !== undefined) params.set('due', String(filters.due))
  if (filters.as_of) params.set('as_of', filters.as_of)
  params.set('limit', String(filters.limit ?? 100))
  return params.toString()
}

/** Every endpoint the UI calls. The four human routes are the only ones that
 *  write a decision or a stage; `aiCheck` is explicit and never called on load. */
export const api = {
  queue: (filters: QueueFilters) =>
    request<QueueResponse>(`/queue?${queueQuery(filters)}`),
  founder: (idOrPath: string) => {
    // callers may append `?as_of=` for read-time simulation
    const [id, query] = idOrPath.split('?')
    return request<FounderDetail>(
      `/founders/${encodeURIComponent(id)}${query ? `?${query}` : ''}`)
  },
  audit: (id: string) =>
    request<{ founder_id: string; events: AuditEvent[] }>(`/audit/${encodeURIComponent(id)}`),
  dashboard: (asOf?: string, stuckDays?: number) => {
    const params = new URLSearchParams()
    if (asOf) params.set('as_of', asOf)
    if (stuckDays !== undefined) params.set('stuck_days', String(stuckDays))
    const query = params.toString()
    return request<Dashboard>(`/dashboard${query ? `?${query}` : ''}`)
  },
  config: () => request<EffectiveConfig>('/config'),

  putConfig: (config: unknown, actor: string) =>
    request<{ rubric_version_before: string; rubric_version: string; rescored: boolean;
              note: string }>('/config', {
      method: 'PUT', body: JSON.stringify({ config, actor }),
    }),

  rescore: (actor: string, reason: string) =>
    request<{ founders_rescored: number; rubric_version: string; assessments_changed: number;
              canonical_profiles_changed: number; human_state_touched: boolean }>('/rescore', {
      method: 'POST', body: JSON.stringify({ actor, reason }),
    }),

  /** Optional AI overlay. Called ONLY from the explicit button — never on load. */
  aiCheck: (id: string) =>
    request<AICheckResponse>(`/founders/${encodeURIComponent(id)}/ai_check`,
                             { method: 'POST' }),

  // ---- human mutations: one endpoint per human act, never bundled ----
  decision: (id: string, disposition: string, actor: string, reason: string) =>
    request<unknown>(`/founders/${encodeURIComponent(id)}/decision`, {
      method: 'POST', body: JSON.stringify({ disposition, actor, reason }),
    }),

  stage: (id: string, stage: Stage, actor: string, reason: string, months?: number) =>
    request<{ from: Stage; to: Stage; keep_warm_until: string | null }>(
      `/founders/${encodeURIComponent(id)}/stage`, {
        method: 'POST',
        body: JSON.stringify(months === undefined
          ? { stage, actor, reason }
          : { stage, actor, reason, months }),
      }),

  note: (id: string, text: string, actor: string) =>
    request<unknown>(`/founders/${encodeURIComponent(id)}/notes`, {
      method: 'POST', body: JSON.stringify({ text, actor }),
    }),

  workflow: (id: string, actor: string, reason: string,
             fields: { owner?: string; next_action?: string }) =>
    request<unknown>(`/founders/${encodeURIComponent(id)}/workflow`, {
      method: 'PATCH', body: JSON.stringify({ actor, reason, ...fields }),
    }),
}
