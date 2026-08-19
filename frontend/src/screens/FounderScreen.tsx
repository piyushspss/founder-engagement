// Screen 2 — Founder Detail: the explanation screen, then the action screen.
// The machine's half is grey and labelled; the human's half is boxed in black.

import { useState } from 'react'
import { api } from '../api'
import { ErrorBox, Loading } from '../components/States'
import { useAsync } from '../useAsync'
import { formatDateTime } from '../vocab'
import ActionPanel from './parts/ActionPanel'
import AIEvidencePanel from './parts/AIEvidencePanel'
import ArchetypePanel from './parts/ArchetypePanel'
import AssessmentCard from './parts/AssessmentCard'
import AuditPanel from './parts/AuditPanel'
import ExceptionalPanel from './parts/ExceptionalPanel'
import SignalsTable from './parts/SignalsTable'
import TimelinePanel from './parts/TimelinePanel'
import UncertaintyPanel from './parts/UncertaintyPanel'

/**
 * S2 Founder Detail.
 *
 * Ordered so authority reads top-to-bottom: machine assessment and its
 * explanation first, then the optional AI overlay in a lighter subordinate
 * frame, then the visually separate HUMAN decision panel, then the audit
 * history. Nothing on this screen derives a machine dimension locally.
 */
export default function FounderScreen({ id, actor }: { id: string; actor: string }) {
  // Read-time simulation, same lens as the queue: it changes what this screen
  // says is due today and writes nothing.
  const [asOf, setAsOf] = useState('')
  const detail = useAsync(
    () => api.founder(asOf ? `${id}?as_of=${asOf}` : id), [id, asOf])
  const audit = useAsync(() => api.audit(id), [id])
  const config = useAsync(() => api.config(), [])

  const reload = () => { detail.reload(); audit.reload() }

  if (detail.loading) return <Loading label="Loading founder…" />
  if (detail.error) return <ErrorBox error={detail.error} onRetry={detail.reload} />
  if (!detail.data) return null

  const d = detail.data
  const decision = d.current_decision

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <a href="#/" className="text-xs text-slate-500 underline">← Priority Queue</a>
          <h1 className="mt-1 break-all text-lg font-semibold text-slate-900">
            {d.facts.canonical.headline || 'Founder'}
          </h1>
          <p className="break-all font-mono text-xs text-slate-500">{d.founder_id}</p>
          <p className="mt-0.5 text-xs text-slate-500">
            Source: {d.facts.source ?? '—'} · Funnel: {d.facts.funnel ?? '—'} ·
            {' '}First seen {formatDateTime(d.facts.created_at)}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-slate-500">Current human disposition</p>
          <p className="text-sm font-semibold text-slate-900">
            {decision ? decision.disposition.replace(/_/g, ' ').toLowerCase() : 'none yet'}
          </p>
          {decision && (
            <p className="text-[11px] text-slate-500">
              by {decision.actor}, {formatDateTime(decision.at)}
            </p>
          )}
          <div className="mt-2 flex items-end justify-end gap-2">
            <label htmlFor="as-of-founder" className="text-[11px] text-slate-500">
              View as of
            </label>
            <input id="as-of-founder" type="date" value={asOf}
                   onChange={(e) => setAsOf(e.target.value)}
                   className="rounded border border-slate-300 px-2 py-1 text-xs" />
          </div>
        </div>
      </div>

      <AssessmentCard detail={d} effectiveRubric={config.data?.rubric_version ?? null} />

      <div className="grid gap-4 xl:grid-cols-2">
        <SignalsTable assessment={d.assessment}
                      weights={config.data?.config.weights.signal_weights ?? null} />
        <div className="space-y-4">
          <ExceptionalPanel assessment={d.assessment} />
          <ArchetypePanel assessment={d.assessment} />
        </div>
      </div>

      <AIEvidencePanel founderId={d.founder_id}
                       status={config.data?.ai_layer ?? null} />

      <UncertaintyPanel detail={d} />
      <TimelinePanel detail={d} />

      <ActionPanel detail={d} actor={actor} onDone={reload} />

      {audit.loading && <Loading label="Loading audit history…" />}
      {audit.error != null && <ErrorBox error={audit.error} onRetry={audit.reload} />}
      {audit.data && <AuditPanel events={audit.data.events} />}
    </div>
  )
}
