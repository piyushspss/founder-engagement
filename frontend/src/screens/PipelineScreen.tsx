// Screen 3 — Pipeline (Kanban) + weekly dashboard + config drawer.
//
// Stage moves are explicit human API calls with a reason. The board offers the
// transitions the BACKEND says are allowed for that founder; the "show every
// stage" escape hatch exists so a rejected move surfaces the API's 409 rather
// than being silently hidden by the UI.

import { useMemo, useState } from 'react'
import { api } from '../api'
import { AttentionBadge, ConfidenceMeter, PotentialChip,
         WorkflowReasonBadge } from '../components/Badges'
import { Banner, Empty, ErrorBox, Loading } from '../components/States'
import type { Dashboard, QueueRow, Stage } from '../types'
import { useAsync } from '../useAsync'
import { STAGE_LABEL, STAGE_ORDER, formatDate, shortId } from '../vocab'
import ConfigDrawer from './parts/ConfigDrawer'

/** Small bar chart for the weekly metrics. */
function Bars({ data, max, label }:
  { data: { key: string; value: number }[]; max: number; label: string }) {
  return (
    <ul aria-label={label} className="space-y-1">
      {data.map((d) => (
        <li key={d.key} className="flex items-center gap-2 text-xs">
          <span className="w-36 shrink-0 truncate text-slate-600">{d.key}</span>
          <span className="h-3 flex-1 overflow-hidden rounded bg-slate-100">
            <span className="block h-full rounded bg-slate-500"
                  style={{ width: max ? `${(d.value / max) * 100}%` : '0%' }} />
          </span>
          <span className="w-10 shrink-0 text-right tabular-nums text-slate-700">
            {d.value}
          </span>
        </li>
      ))}
    </ul>
  )
}

/** One dashboard metric tile. */
function Tile({ label, value, hint }: { label: string; value: string | number; hint: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">{value}</p>
      <p className="mt-1 text-[11px] leading-tight text-slate-500">{hint}</p>
    </div>
  )
}

/**
 * S3 Pipeline & Dashboard.
 *
 * Kanban by stage with explicit, reason-carrying moves — there is no drag-drop
 * shortcut, because a stage change is a human act that must carry a reason.
 * The config drawer edits weights, thresholds and tier lists; SAVING CONFIG
 * NEVER RESCORES, and a founder whose stored rubric differs from the effective
 * one is labelled "Assessment needs recalculation" rather than silently
 * re-displayed. F-19: each column renders at most 25 cards and says so.
 */
export default function PipelineScreen({ actor }: { actor: string }) {
  const [version, setVersion] = useState(0)
  const [drawer, setDrawer] = useState(false)
  // A rejected move must be readable even though the board column scrolls, so
  // the API's refusal is surfaced above the board as well as inside the card.
  const [moveError, setMoveError] = useState<unknown>(null)
  //(read-time simulation only — `as_of` never writes anything)
  const [asOf, setAsOf] = useState('')
  const [stuckDays, setStuckDays] = useState('')
  const dash = useAsync<Dashboard>(
    () => api.dashboard(asOf || undefined, stuckDays ? Number(stuckDays) : undefined),
    [version, asOf, stuckDays])
  const board = useAsync(() => api.queue({ limit: 1000, as_of: asOf || undefined }),
                         [version, asOf])
  const config = useAsync(() => api.config(), [version])

  const byStage = useMemo(() => {
    const map = new Map<Stage, QueueRow[]>()
    STAGE_ORDER.forEach((s) => map.set(s, []))
    board.data?.rows.forEach((r) => {
      if (r.stage) map.get(r.stage)?.push(r)
    })
    return map
  }, [board.data])

  // Histogram of the confidence values the API returned. Bucketing is display,
  // not policy — no threshold is invented here.
  const confidenceHistogram = useMemo(() => {
    const buckets = ['0.0–0.2', '0.2–0.4', '0.4–0.6', '0.6–0.8', '0.8–1.0']
    const counts = [0, 0, 0, 0, 0]
    board.data?.rows.forEach((r) => {
      const i = Math.min(4, Math.floor((r.confidence ?? 0) / 0.2))
      counts[i] += 1
    })
    return buckets.map((key, i) => ({ key, value: counts[i] }))
  }, [board.data])

  const refresh = () => setVersion((v) => v + 1)

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Pipeline &amp; Dashboard</h1>
          <p className="text-sm text-slate-500">
            Where every founder stands, and how the week looks.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="as-of-pipeline"
                   className="block text-[11px] font-medium text-slate-500">
              View as of
            </label>
            <input id="as-of-pipeline" type="date" value={asOf}
                   onChange={(e) => setAsOf(e.target.value)}
                   className="mt-0.5 rounded border border-slate-300 px-2 py-1 text-xs" />
          </div>
          <div>
            <label htmlFor="stuck-days"
                   className="block text-[11px] font-medium text-slate-500">
              Stuck after (days)
            </label>
            <input id="stuck-days" type="number" min={1} value={stuckDays}
                   placeholder={String(dash.data?.stuck.threshold_days ?? 14)}
                   onChange={(e) => setStuckDays(e.target.value)}
                   className="mt-0.5 w-24 rounded border border-slate-300 px-2 py-1
                              text-xs" />
          </div>
          {config.data && (
            <span className="self-center font-mono text-[11px] text-slate-500">
              rubric {config.data.rubric_version.slice(0, 12)}…
            </span>
          )}
          <button type="button" onClick={() => setDrawer(true)}
                  className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm
                             font-medium hover:bg-slate-100">
            Configuration
          </button>
        </div>
      </div>

      {/* ------------------------------ Kanban ------------------------------ */}
      <section aria-labelledby="pipeline-heading">
        <h2 id="pipeline-heading" className="text-sm font-semibold text-slate-800">
          Pipeline
        </h2>
        <p className="text-[11px] text-slate-500">
          Stage is human-owned. Moving a card calls the API with a reason and is audited;
          transitions the workflow does not allow are refused by the API.
        </p>
        {moveError != null && (
          <div className="mt-2" data-testid="board-move-error">
            <ErrorBox error={moveError} />
          </div>
        )}
        {board.loading && !board.data && <Loading label="Loading pipeline…" />}
        {board.error != null && <ErrorBox error={board.error} onRetry={board.reload} />}
        {board.data && (
          <div className="mt-2 grid gap-2 overflow-x-auto md:grid-cols-4 xl:grid-cols-7">
            {STAGE_ORDER.map((stage) => {
              const rows = byStage.get(stage) ?? []
              return (
                <div key={stage}
                     className="min-w-[190px] rounded-lg border border-slate-200 bg-slate-50 p-2">
                  <h3 className="flex items-baseline justify-between text-xs font-semibold
                                 text-slate-700">
                    {STAGE_LABEL[stage]}
                    <span className="tabular-nums text-slate-500">{rows.length}</span>
                  </h3>
                  <ul className="mt-1.5 max-h-[380px] space-y-1.5 overflow-y-auto">
                    {rows.slice(0, 25).map((row) => (
                      <li key={row.founder_id}>
                        <Card row={row} actor={actor} onMoved={refresh}
                              onError={setMoveError} />
                      </li>
                    ))}
                    {rows.length === 0 && (
                      <li className="p-2 text-[11px] text-slate-400">Empty</li>
                    )}
                    {rows.length > 25 && (
                      <li className="p-1 text-[11px] text-slate-500">
                        +{rows.length - 25} more
                      </li>
                    )}
                  </ul>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* ----------------------------- dashboard ---------------------------- */}
      {dash.loading && !dash.data && <Loading label="Loading dashboard…" />}
      {dash.error != null && <ErrorBox error={dash.error} onRetry={dash.reload} />}
      {dash.data && (
        <section aria-labelledby="dashboard-heading" className="space-y-3">
          <h2 id="dashboard-heading" className="text-sm font-semibold text-slate-800">
            Weekly review — as of {formatDate(dash.data.as_of)}
            {asOf && (
              <span className="ml-2 rounded border border-slate-400 px-1.5 py-0.5 text-[11px]
                               font-normal text-slate-600">
                simulated date — read only, nothing is written
              </span>
            )}
          </h2>

          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Tile label="Founders" value={dash.data.founders} hint="In the database" />
            <Tile label="Review queue" value={dash.data.review_queue_size}
                  hint="Priority Review + Review" />
            <Tile label="Re-engagement due" value={dash.data.re_engagement_due}
                  hint="Keep-warm date reached — a human commitment, not a machine signal" />
            <Tile label={`Stuck > ${dash.data.stuck.threshold_days} days`}
                  value={dash.data.stuck.count}
                  hint={`In the same stage longer than ${dash.data.stuck.threshold_days} days. `
                      + `Excludes ${dash.data.stuck.excluded_stages
                        .map((s2) => STAGE_LABEL[s2 as Stage] ?? s2).join(', ')}.`} />
            <Tile label="Low evidence confidence"
                  value={`${dash.data.low_confidence_pct}%`}
                  hint={`Below ${dash.data.low_confidence_threshold}`} />
            <Tile label="Human decisions" value={dash.data.human_decisions_recorded}
                  hint="Founders with a recorded disposition" />
            {dash.data.keep_warm_inconsistent > 0 && (
              <Tile label="Inconsistent keep-warm"
                    value={dash.data.keep_warm_inconsistent}
                    hint="Keep warm with no date — reported, never guessed, never due" />
            )}
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <h3 className="mb-2 text-xs font-semibold text-slate-700">Stage counts</h3>
              <Bars label="Stage counts"
                    data={STAGE_ORDER.map((s) => ({ key: STAGE_LABEL[s],
                                                    value: dash.data!.stage_counts[s] ?? 0 }))}
                    max={Math.max(...Object.values(dash.data.stage_counts), 1)} />
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <h3 className="mb-2 text-xs font-semibold text-slate-700">Intake by week</h3>
              <Bars label="Weekly intake"
                    data={dash.data.weekly_intake.map((w) => ({ key: w.week_starting,
                                                                value: w.count }))}
                    max={Math.max(...dash.data.weekly_intake.map((w) => w.count), 1)} />
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <h3 className="mb-2 text-xs font-semibold text-slate-700">
                Ageing in current stage
              </h3>
              <Bars label="Ageing"
                    data={Object.entries(dash.data.ageing_in_stage)
                      .map(([key, value]) => ({ key, value }))}
                    max={Math.max(...Object.values(dash.data.ageing_in_stage), 1)} />
              <p className="mt-1 text-[11px] text-slate-500">
                Median {dash.data.median_days_in_stage} days.
              </p>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <h3 className="mb-2 text-xs font-semibold text-slate-700">
                Attention distribution
              </h3>
              <Bars label="Attention distribution"
                    data={(['PRIORITY_REVIEW', 'REVIEW', 'ROUTINE'] as const).map((k) => ({
                      key: k.replace('_', ' ').toLowerCase(),
                      value: dash.data!.attention_distribution[k] ?? 0 }))}
                    max={Math.max(...Object.values(dash.data.attention_distribution), 1)} />
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <h3 className="mb-2 text-xs font-semibold text-slate-700">
                Evidence confidence distribution
              </h3>
              <Bars label="Confidence distribution" data={confidenceHistogram}
                    max={Math.max(...confidenceHistogram.map((b) => b.value), 1)} />
              <p className="mt-1 text-[11px] text-slate-500">
                Bucketed from the confidence values the API returned.
              </p>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <h3 className="mb-1 text-xs font-semibold text-slate-700">Potential</h3>
              <p className="mb-2 text-[11px] text-slate-500">
                Asserted judgments and unmade judgments are counted separately — Unknown is
                not a lower grade than Low.
              </p>
              <Bars label="Asserted potential"
                    data={(['HIGH', 'MEDIUM', 'LOW'] as const).map((k) => ({
                      key: k.toLowerCase(),
                      value: dash.data!.potential_distribution[k] ?? 0 }))}
                    max={Math.max(...Object.values(dash.data.potential_distribution), 1)} />
              <p className="mt-2 rounded border border-dashed border-violet-300 bg-violet-50
                            px-2 py-1 text-[11px] text-violet-900">
                Not asserted — insufficient evidence to judge:
                {' '}<strong className="tabular-nums">
                  {dash.data.potential_distribution.UNKNOWN ?? 0}
                </strong>
              </p>
            </div>
          </div>
        </section>
      )}

      {config.data && (
        <ConfigDrawer open={drawer} onClose={() => setDrawer(false)} config={config.data}
                      actor={actor} onSaved={() => config.reload()} onRescored={refresh} />
      )}
      {config.error != null && <ErrorBox error={config.error} onRetry={config.reload} />}
    </div>
  )
}

/** One founder card in a Kanban column. */
function Card({ row, actor, onMoved, onError }:
  { row: QueueRow; actor: string; onMoved: () => void; onError: (e: unknown) => void }) {
  const [open, setOpen] = useState(false)
  const [allowed, setAllowed] = useState<Stage[] | null>(null)
  const [showAll, setShowAll] = useState(false)
  const [target, setTarget] = useState<Stage | ''>('')
  const [reason, setReason] = useState('')
  const [months, setMonths] = useState(6)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  const openForm = async () => {
    setOpen(true); setError(null); onError(null)
    try {
      const detail = await api.founder(row.founder_id)
      setAllowed(detail.workflow?.allowed_transitions ?? [])
    } catch (e) {
      setError(e)
    }
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!target) return
    setBusy(true); setError(null); onError(null)
    try {
      await api.stage(row.founder_id, target, actor, reason,
        target === 'KEEP_WARM' ? months : undefined)
      setOpen(false); setReason(''); setTarget('')
      onMoved()
    } catch (err) {
      setError(err)
      onError(err)
    } finally {
      setBusy(false)
    }
  }

  const options = showAll ? STAGE_ORDER : (allowed ?? [])

  return (
    <div className="rounded border border-slate-200 bg-white p-2">
      <a href={`#/founders/${encodeURIComponent(row.founder_id)}`}
         className="block font-mono text-[11px] text-slate-700 underline">
        {shortId(row.founder_id)}
      </a>
      <div className="mt-1 flex flex-wrap items-center gap-1">
        <AttentionBadge value={row.attention} />
        <PotentialChip value={row.potential} />
      </div>
      <div className="mt-1 flex items-center justify-between">
        <ConfidenceMeter value={row.confidence} compact />
        <span className="text-[11px] text-slate-500">{row.owner ?? 'unassigned'}</span>
      </div>
      {row.workflow_reasons.map((reason) => (
        <div key={reason} className="mt-1"><WorkflowReasonBadge reason={reason} /></div>
      ))}
      {row.keep_warm_until && (
        <p className="mt-0.5 text-[11px] text-slate-500">
          {row.due ? 'due ' : 'warm until '}{formatDate(row.keep_warm_until)}
        </p>
      )}

      {!open ? (
        <div className="mt-1.5 space-y-1">
          {row.stage === 'KEEP_WARM' && (
            <button type="button" data-testid="board-reengage"
                    onClick={() => { void openForm(); setTarget('NURTURING') }}
                    className="w-full rounded bg-amber-800 px-2 py-1 text-[11px] font-medium
                               text-white">
              {row.due ? 'Re-engage' : 'Re-engage early'}
            </button>
          )}
          <button type="button" onClick={() => void openForm()}
                  className="w-full rounded border border-slate-300 px-2 py-1 text-[11px]
                             hover:bg-slate-100">
            Move stage…
          </button>
        </div>
      ) : (
        <form onSubmit={submit} className="mt-1.5 space-y-1.5">
          <label htmlFor={`t-${row.founder_id}`} className="sr-only">Target stage</label>
          <select id={`t-${row.founder_id}`} value={target}
                  onChange={(e) => setTarget(e.target.value as Stage | '')}
                  className="w-full rounded border border-slate-300 px-1.5 py-1 text-[11px]">
            <option value="">Choose…</option>
            {options.map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
          </select>
          {target === 'KEEP_WARM' && (
            <>
              <label htmlFor={`m-${row.founder_id}`} className="sr-only">Keep warm months</label>
              <select id={`m-${row.founder_id}`} value={months}
                      onChange={(e) => setMonths(Number(e.target.value))}
                      className="w-full rounded border border-slate-300 px-1.5 py-1
                                 text-[11px]">
                {[3, 6, 9].map((m) => <option key={m} value={m}>{m} months</option>)}
              </select>
            </>
          )}
          <label htmlFor={`r-${row.founder_id}`} className="sr-only">Reason</label>
          <input id={`r-${row.founder_id}`} required value={reason} placeholder="Reason"
                 onChange={(e) => setReason(e.target.value)}
                 className="w-full rounded border border-slate-300 px-1.5 py-1 text-[11px]" />
          <label className="flex items-center gap-1 text-[11px] text-slate-500">
            <input type="checkbox" checked={showAll}
                   onChange={(e) => setShowAll(e.target.checked)} />
            Show every stage (the API will refuse disallowed moves)
          </label>
          <div className="flex gap-1">
            <button type="submit" disabled={busy}
                    className="rounded bg-slate-900 px-2 py-1 text-[11px] text-white
                               disabled:opacity-50">
              {busy ? 'Moving…' : 'Move'}
            </button>
            <button type="button"
                    onClick={() => { setOpen(false); setError(null); onError(null) }}
                    className="rounded border border-slate-300 px-2 py-1 text-[11px]">
              Cancel
            </button>
          </div>
          {allowed?.length === 0 && !showAll && (
            <Banner tone="info">Closed is terminal — no onward transition.</Banner>
          )}
          {error != null && (
            <p role="alert" className="rounded border border-rose-300 bg-rose-50 px-1.5 py-1
                                       text-[11px] text-rose-900">
              Refused by the API — see the message above the board.
            </p>
          )}
        </form>
      )}
    </div>
  )
}

export { Empty }
