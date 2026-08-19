// Audit history. A system RESCORE must be unmistakable from a human act, and it
// must never look like it moved the workflow.

import type { AuditEvent } from '../../types'
import { formatDateTime } from '../../vocab'

/** Events that represent a HUMAN act, labelled distinctly from machine ones. */
const HUMAN_EVENT_LABEL: Record<string, string> = {
  DECISION: 'Disposition',
  STAGE: 'Stage',
  NOTE: 'Note',
  WORKFLOW: 'Workflow field',
}

/**
 * The audit history. Human events (decision, stage, note) are labelled
 * distinctly from machine events (rescore), so "the model changed its mind" and
 * "a person made a call" are never confused. The optional AI layer appears
 * nowhere here — it creates no audit event by design.
 */
export default function AuditPanel({ events }: { events: AuditEvent[] }) {
  return (
    <section aria-labelledby="audit-heading"
             className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="audit-heading" className="text-base font-semibold text-slate-900">
        Audit history
      </h2>
      {events.length === 0 ? (
        <p className="mt-2 text-xs text-slate-500">
          No changes yet. Import and assessment never create a human decision.
        </p>
      ) : (
        <ol className="mt-2 space-y-1.5">
          {[...events].reverse().map((e) => {
            const system = e.event === 'RESCORE'
            return (
              <li key={e.id}
                  data-testid={system ? 'audit-system' : 'audit-human'}
                  className={`rounded border p-2 text-xs ${
                    system ? 'border-slate-200 bg-slate-50' : 'border-slate-200 bg-white'}`}>
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                    system ? 'bg-slate-200 text-slate-700' : 'bg-slate-900 text-white'}`}>
                    {system ? 'System' : 'Human'}
                  </span>
                  <span className="font-medium text-slate-900">{e.actor}</span>
                  <span className="text-slate-700">
                    {system
                      ? '— assessment recalculated (machine only; workflow untouched)'
                      : `— ${HUMAN_EVENT_LABEL[e.event] ?? e.event}: ${e.field}`}
                  </span>
                  <span className="ml-auto text-[11px] text-slate-500">
                    {formatDateTime(e.at)}
                  </span>
                </div>
                <p className="mt-0.5 text-slate-700">
                  <span className="font-mono text-[11px]">{e.from ?? '—'}</span>
                  <span aria-hidden> → </span>
                  <span className="sr-only">changed to</span>
                  <span className="font-mono text-[11px] font-semibold">{e.to ?? '—'}</span>
                </p>
                {e.reason && <p className="mt-0.5 text-slate-600">Reason: {e.reason}</p>}
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
