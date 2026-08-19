// Screen 1 — Priority Queue (home).
//
// Answers, in one view: who needs my attention today, why are they here, and
// what should I do next. Ordering comes from the API (attention, then evidence
// confidence descending, then id) — the client never re-ranks, and never ranks
// by potential.

import { useMemo, useState } from 'react'
import { api, type QueueFilters } from '../api'
import {
  ActionText, AttentionBadge, ConfidenceMeter, DataStateTag, PotentialChip,
  WorkflowReasonBadge,
} from '../components/Badges'
import { Empty, ErrorBox, Loading } from '../components/States'
import type { Dashboard, QueueRow } from '../types'
import { formatDate, formatWhy, shortId, STAGE_LABEL, STAGE_ORDER } from '../vocab'
import { useAsync } from '../useAsync'

/** Filter options — sent server-side, never applied locally. */
const ATTENTION_OPTIONS = ['PRIORITY_REVIEW', 'REVIEW', 'ROUTINE'] as const
const DATA_STATE_OPTIONS = ['SUFFICIENT', 'PARTIAL', 'NEEDS_INFORMATION'] as const

/** One KPI tile in the dashboard strip. */
function Kpi({ label, value, hint, onClick, active }:
  { label: string; value: number | string; hint: string; onClick?: () => void;
    active?: boolean }) {
  const body = (
    <>
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</p>
      <p className="mt-1 text-[11px] leading-tight text-slate-500">{hint}</p>
    </>
  )
  const shell = 'rounded-lg border bg-white p-3 text-left w-full'
  if (!onClick) {
    return <div className={`${shell} border-slate-200`}>{body}</div>
  }
  return (
    <button type="button" onClick={onClick} aria-pressed={active}
            className={`${shell} ${active ? 'border-slate-900 ring-1 ring-slate-900'
              : 'border-slate-200 hover:border-slate-400'}`}>
      {body}
    </button>
  )
}

/**
 * S1 Priority Queue (home).
 *
 * The table renders rows in exactly the order the API returned them
 * (attention → evidence confidence → id). POTENTIAL IS NEVER THE RANKING KEY,
 * and the client never re-sorts or re-filters — every filter is a server-side
 * query parameter, so what a reviewer sees is what the policy decided.
 */
export default function QueueScreen({ actor: _actor }: { actor: string }) {
  const [attention, setAttention] = useState<string[]>([])
  const [dataState, setDataState] = useState<string[]>([])
  const [stage, setStage] = useState<string[]>([])
  const [owner, setOwner] = useState('')
  const [due, setDue] = useState(false)
  const [asOf, setAsOf] = useState('')

  const filters: QueueFilters = useMemo(() => ({
    attention: attention.length ? attention : undefined,
    data_state: dataState.length ? dataState : undefined,
    stage: stage.length ? stage : undefined,
    owner: owner || undefined,
    due: due ? true : undefined,
    as_of: asOf || undefined,
    limit: 200,
  }), [attention, dataState, stage, owner, due, asOf])

  const key = JSON.stringify(filters)
  const queue = useAsync(() => api.queue(filters), [key])
  const dash = useAsync<Dashboard>(() => api.dashboard(asOf || undefined), [asOf])

  const toggle = (list: string[], set: (v: string[]) => void, value: string) =>
    set(list.includes(value) ? list.filter((v) => v !== value) : [...list, value])

  const clearAll = () => {
    setAttention([]); setDataState([]); setStage([]); setOwner(''); setDue(false); setAsOf('')
  }
  const anyFilter = attention.length || dataState.length || stage.length || owner || due || asOf

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Priority Queue</h1>
        <p className="text-sm text-slate-500">
          Who needs attention today, why they are here, and what to do next.
          The machine prioritises; you decide.
        </p>
      </div>

      {/* ---- KPI strip: every number comes straight from /dashboard ---- */}
      {dash.data && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Kpi label="Priority Review"
               value={dash.data.attention_distribution.PRIORITY_REVIEW ?? 0}
               hint="Machine attention — exceptional or strong, well-covered evidence"
               active={attention.includes('PRIORITY_REVIEW')}
               onClick={() => toggle(attention, setAttention, 'PRIORITY_REVIEW')} />
          <Kpi label="Re-engagement Due" value={dash.data.re_engagement_due}
               hint="Workflow — a keep-warm date a person set has arrived"
               active={due}
               onClick={() => setDue(!due)} />
          <Kpi label="Needs Research / Information"
               value={dash.data.data_state_distribution.NEEDS_INFORMATION ?? 0}
               hint="Machine data state — experience history missing or incomplete"
               active={dataState.includes('NEEDS_INFORMATION')}
               onClick={() => toggle(dataState, setDataState, 'NEEDS_INFORMATION')} />
          <Kpi label="Nurturing" value={dash.data.stage_counts.NURTURING}
               hint="Workflow stage — in an active human workflow"
               active={stage.includes('NURTURING')}
               onClick={() => setStage(stage.includes('NURTURING') ? [] : ['NURTURING'])} />
        </div>
      )}

      {/* ---- filters: every one is a server-side query parameter ---- */}
      <section aria-labelledby="filters-heading"
               className="rounded-lg border border-slate-200 bg-white p-3">
        <div className="flex items-center justify-between">
          <h2 id="filters-heading" className="text-sm font-semibold text-slate-800">
            Filters
          </h2>
          {anyFilter ? (
            <button type="button" onClick={clearAll}
                    className="text-xs font-medium text-slate-600 underline">
              Clear all
            </button>
          ) : null}
        </div>
        <div className="mt-3 flex flex-wrap items-start gap-x-6 gap-y-3">
          <fieldset>
            <legend className="text-xs font-medium text-slate-500">Attention</legend>
            <div className="mt-1 flex gap-1">
              {ATTENTION_OPTIONS.map((value) => (
                <label key={value}
                       className={`cursor-pointer rounded border px-2 py-1 text-xs ${
                         attention.includes(value)
                           ? 'border-slate-800 bg-slate-800 text-white'
                           : 'border-slate-300 bg-white text-slate-700'}`}>
                  <input type="checkbox" className="sr-only"
                         checked={attention.includes(value)}
                         onChange={() => toggle(attention, setAttention, value)} />
                  {value.replace('_', ' ').toLowerCase()}
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend className="text-xs font-medium text-slate-500">Data state</legend>
            <div className="mt-1 flex gap-1">
              {DATA_STATE_OPTIONS.map((value) => (
                <label key={value}
                       className={`cursor-pointer rounded border px-2 py-1 text-xs ${
                         dataState.includes(value)
                           ? 'border-slate-800 bg-slate-800 text-white'
                           : 'border-slate-300 bg-white text-slate-700'}`}>
                  <input type="checkbox" className="sr-only"
                         checked={dataState.includes(value)}
                         onChange={() => toggle(dataState, setDataState, value)} />
                  {value.replace('_', ' ').toLowerCase()}
                </label>
              ))}
            </div>
          </fieldset>

          <div>
            <label htmlFor="stage-filter" className="block text-xs font-medium text-slate-500">
              Stage
            </label>
            <select id="stage-filter" value={stage[0] ?? ''}
                    onChange={(e) => setStage(e.target.value ? [e.target.value] : [])}
                    className="mt-1 rounded border border-slate-300 px-2 py-1 text-xs">
              <option value="">All stages</option>
              {STAGE_ORDER.map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
            </select>
          </div>

          <div>
            <label htmlFor="owner-filter" className="block text-xs font-medium text-slate-500">
              Owner
            </label>
            <input id="owner-filter" value={owner} placeholder="any"
                   onChange={(e) => setOwner(e.target.value)}
                   className="mt-1 w-28 rounded border border-slate-300 px-2 py-1 text-xs" />
          </div>

          <div>
            <span className="block text-xs font-medium text-slate-500">Re-engagement</span>
            <label className="mt-1 flex items-center gap-1.5 text-xs text-slate-700">
              <input type="checkbox" checked={due} onChange={(e) => setDue(e.target.checked)} />
              Due only
            </label>
          </div>

          <div>
            <label htmlFor="as-of" className="block text-xs font-medium text-slate-500">
              As of date
            </label>
            <input id="as-of" type="date" value={asOf}
                   onChange={(e) => setAsOf(e.target.value)}
                   className="mt-1 rounded border border-slate-300 px-2 py-1 text-xs" />
          </div>
        </div>
      </section>

      {/* ---- the queue ---- */}
      {queue.loading && <Loading label="Loading queue…" />}
      {queue.error != null && <ErrorBox error={queue.error} onRetry={queue.reload} />}
      {queue.data && queue.data.rows.length === 0 && (
        <Empty title="No founders match these filters."
               hint="Clear a filter, or change the as-of date if you are looking for
                     re-engagement due." />
      )}

      {queue.data && queue.data.rows.length > 0 && (
        <>
          <p className="text-xs text-slate-500">
            Showing {queue.data.rows.length} of {queue.data.total}. Sorted by attention
            (Priority Review → Review → Routine), then evidence confidence, then id.
            <strong className="font-medium"> Potential is never the ranking key.</strong>
            {' '}Workflow obligations such as <em>Re-engagement due</em> appear in the stage
            column — they never alter the machine assessment or its ordering.
          </p>
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full min-w-[1100px] text-left text-sm">
              <caption className="sr-only">
                Founder priority queue, ordered by attention then evidence confidence
              </caption>
              <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase
                                tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="px-3 py-2">Founder</th>
                  <th scope="col" className="px-3 py-2">Attention</th>
                  <th scope="col" className="px-3 py-2">Potential</th>
                  <th scope="col" className="px-3 py-2">Evidence confidence</th>
                  <th scope="col" className="px-3 py-2">Data state</th>
                  <th scope="col" className="px-3 py-2">Archetype</th>
                  <th scope="col" className="px-3 py-2">
                    Why surfaced <span className="font-normal normal-case">(machine)</span>
                  </th>
                  <th scope="col" className="px-3 py-2">Recommended action</th>
                  <th scope="col" className="px-3 py-2">
                    Stage <span className="font-normal normal-case">&amp; workflow</span>
                  </th>
                  <th scope="col" className="px-3 py-2">Owner</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {queue.data.rows.map((row) => <Row key={row.founder_id} row={row} />)}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

/** One queue row. Machine columns and human/workflow columns are rendered as
 *  visibly separate groups. */
function Row({ row }: { row: QueueRow }) {
  const why = row.why_surfaced.map(formatWhy)
  return (
    <tr className="align-top hover:bg-slate-50">
      <td className="px-3 py-2">
        <a href={`#/founders/${encodeURIComponent(row.founder_id)}`}
           className="font-medium text-slate-900 underline decoration-slate-300
                      underline-offset-2">
          {shortId(row.founder_id)}
        </a>
        <div className="text-[11px] text-slate-400">
          v{row.assessment_version}
          {row.duplicate_count > 0 && ` · ${row.duplicate_count} possible duplicate(s)`}
        </div>
      </td>
      <td className="px-3 py-2"><AttentionBadge value={row.attention} /></td>
      <td className="px-3 py-2"><PotentialChip value={row.potential} /></td>
      <td className="px-3 py-2"><ConfidenceMeter value={row.confidence} /></td>
      <td className="px-3 py-2"><DataStateTag value={row.data_state} /></td>
      <td className="px-3 py-2 text-xs text-slate-700">{row.archetype ?? '—'}</td>
      <td className="max-w-[280px] px-3 py-2">
        <div className="text-xs text-slate-800">{why[0] ?? '—'}</div>
        {why.length > 1 && (
          <details className="mt-0.5">
            <summary className="cursor-pointer text-[11px] text-slate-500">
              +{why.length - 1} more
            </summary>
            <ul className="mt-1 list-disc pl-4 text-[11px] text-slate-600">
              {why.slice(1).map((w) => <li key={w}>{w}</li>)}
            </ul>
          </details>
        )}
      </td>
      <td className="px-3 py-2"><ActionText value={row.recommended_action} /></td>
      <td className="px-3 py-2 text-xs text-slate-700">
        {row.stage ? STAGE_LABEL[row.stage] : '—'}
        {row.workflow_reasons.map((reason) => (
          <div key={reason} className="mt-1">
            <WorkflowReasonBadge reason={reason} />
          </div>
        ))}
        {row.keep_warm_until && (
          <div className="mt-0.5 text-[11px] text-slate-500">
            {row.due ? 'due ' : 'warm until '}{formatDate(row.keep_warm_until)}
          </div>
        )}
      </td>
      <td className="px-3 py-2 text-xs text-slate-700">{row.owner ?? '—'}</td>
    </tr>
  )
}
