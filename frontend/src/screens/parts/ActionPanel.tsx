// The human action panel — the hard boundary.
//
// Four separate forms, four separate API calls. There is deliberately NO
// "accept the recommendation" button: `recommended_action = CONSIDER_ENGAGEMENT`
// is a suggestion to a person, not a permission slip to write a disposition or
// move a stage. A reviewer who wants to do both things does both things, with a
// reason for each, and the audit log shows two human acts.

import { useState } from 'react'
import { api, ApiError } from '../../api'
import { ErrorBox } from '../../components/States'
import type { Disposition, FounderDetail, Stage } from '../../types'
import { WorkflowReasonBadge } from '../../components/Badges'
import { DISPOSITION_LABEL, STAGE_LABEL, formatDate } from '../../vocab'

/** The four human dispositions. */
const DISPOSITIONS: Disposition[] = [
  'NEEDS_REVIEW', 'POTENTIAL', 'NOT_NOW', 'NEEDS_INFORMATION',
]
/** The only keep-warm durations the API accepts. */
const KEEP_WARM_MONTHS = [3, 6, 9] as const

/** Labelled form field with an optional hint. */
function Field({ label, htmlFor, children, hint }:
  { label: string; htmlFor: string; children: React.ReactNode; hint?: string }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="block text-xs font-medium text-slate-700">
        {label}
      </label>
      {children}
      {hint && <p className="mt-0.5 text-[11px] text-slate-500">{hint}</p>}
    </div>
  )
}

/**
 * The human decision panel — the authority boundary made visible.
 *
 * Disposition, stage, notes and owner/next-action are four SEPARATE forms with
 * four separate reasons and four separate API calls. There is no "accept the
 * recommendation" shortcut, and re-engage is an explicit stage move to
 * NURTURING rather than a special machine event.
 */
export default function ActionPanel(
  { detail, actor, onDone }: { detail: FounderDetail; actor: string; onDone: () => void },
) {
  const wf = detail.workflow
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [ok, setOk] = useState<string | null>(null)

  const [disposition, setDisposition] = useState<Disposition>('NEEDS_REVIEW')
  const [dispositionReason, setDispositionReason] = useState('')

  const [targetStage, setTargetStage] = useState<Stage | ''>('')
  const [stageReason, setStageReason] = useState('')
  const [months, setMonths] = useState<number>(6)

  const [owner, setOwner] = useState(wf?.owner ?? '')
  const [nextAction, setNextAction] = useState(wf?.next_action ?? '')
  const [workflowReason, setWorkflowReason] = useState('')

  const [note, setNote] = useState('')

  const run = async (name: string, fn: () => Promise<unknown>, success: string) => {
    setBusy(name); setError(null); setOk(null)
    try {
      await fn()
      setOk(success)
      onDone()
    } catch (e) {
      setError(e)
      if (!(e instanceof ApiError)) throw e
    } finally {
      setBusy(null)
    }
  }

  const id = detail.founder_id
  const allowed = wf?.allowed_transitions ?? []

  return (
    <section aria-labelledby="human-heading"
             data-testid="human-decision-panel"
             className="rounded-lg border-2 border-slate-900 bg-white p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="human-heading" className="text-base font-semibold text-slate-900">
          Human decision
        </h2>
        <p className="text-[11px] text-slate-500">
          Only these actions change disposition or workflow. The assessment never does.
        </p>
      </div>

      {error != null && <div className="mt-3"><ErrorBox error={error} /></div>}
      {ok && (
        <p role="status" className="mt-3 rounded border border-emerald-300 bg-emerald-50
                                    px-2.5 py-1.5 text-xs text-emerald-900">
          {ok}
        </p>
      )}

      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        {/* -------- disposition -------- */}
        <form className="space-y-2 rounded border border-slate-200 p-3"
              onSubmit={(e) => {
                e.preventDefault()
                void run('decision',
                  () => api.decision(id, disposition, actor, dispositionReason),
                  `Disposition recorded: ${DISPOSITION_LABEL[disposition]}`)
              }}>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Record a disposition
          </h3>
          <Field label="Disposition" htmlFor="disposition">
            <select id="disposition" value={disposition}
                    onChange={(e) => setDisposition(e.target.value as Disposition)}
                    className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm">
              {DISPOSITIONS.map((d) =>
                <option key={d} value={d}>{DISPOSITION_LABEL[d]}</option>)}
            </select>
          </Field>
          <Field label="Reason (required)" htmlFor="disposition-reason">
            <input id="disposition-reason" required value={dispositionReason}
                   onChange={(e) => setDispositionReason(e.target.value)}
                   className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
          </Field>
          <button type="submit" disabled={busy !== null}
                  className="rounded bg-slate-900 px-3 py-1.5 text-xs font-medium text-white
                             disabled:opacity-50">
            {busy === 'decision' ? 'Saving…' : 'Record disposition'}
          </button>
          {detail.current_decision && (
            <p className="text-[11px] text-slate-500">
              Current: {DISPOSITION_LABEL[detail.current_decision.disposition]} —
              {' '}{detail.current_decision.actor}
            </p>
          )}
        </form>

        {/* -------- stage -------- */}
        <form className="space-y-2 rounded border border-slate-200 p-3"
              onSubmit={(e) => {
                e.preventDefault()
                if (!targetStage) return
                void run('stage',
                  () => api.stage(id, targetStage, actor, stageReason,
                    targetStage === 'KEEP_WARM' ? months : undefined),
                  `Stage moved to ${STAGE_LABEL[targetStage]}`)
              }}>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Move stage
          </h3>
          <p className="text-[11px] text-slate-500">
            Current: <strong>{wf ? STAGE_LABEL[wf.stage] : '—'}</strong>
            {wf?.keep_warm_until && ` · warm until ${formatDate(wf.keep_warm_until)}`}
          </p>
          {wf?.workflow_reasons?.map((reason) => (
            <div key={reason}><WorkflowReasonBadge reason={reason} /></div>
          ))}
          {wf?.stage === 'KEEP_WARM' && (
            <div className="rounded border border-amber-300 bg-amber-50 p-2">
              <p className="text-[11px] text-amber-900">
                {wf.due
                  ? 'The keep-warm date has arrived. Re-engaging moves this founder back to '
                    + 'Nurturing and clears the schedule.'
                  : `Warm until ${formatDate(wf.keep_warm_until)}. You can re-engage early — `
                    + 'the workflow allows it — but this founder is not counted as due.'}
              </p>
              <button type="button" data-testid="reengage-button"
                      onClick={() => setTargetStage('NURTURING')}
                      className="mt-1.5 rounded bg-amber-800 px-2.5 py-1 text-xs font-medium
                                 text-white">
                {wf.due ? 'Re-engage' : 'Re-engage early'}
              </button>
              <span className="ml-2 text-[11px] text-amber-900">
                — then give a reason and confirm below.
              </span>
            </div>
          )}
          <Field label="Move to" htmlFor="stage-target"
                 hint={allowed.length === 0
                   ? 'Closed is terminal — no onward transition.'
                   : 'Only transitions the workflow allows are listed.'}>
            <select id="stage-target" value={targetStage}
                    onChange={(e) => setTargetStage(e.target.value as Stage | '')}
                    className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm">
              <option value="">Choose a stage…</option>
              {allowed.map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
            </select>
          </Field>
          {targetStage === 'KEEP_WARM' && (
            <Field label="Keep warm for" htmlFor="keep-warm-months"
                   hint="Sets the re-engagement date. 3, 6 or 9 months only.">
              <select id="keep-warm-months" value={months}
                      onChange={(e) => setMonths(Number(e.target.value))}
                      className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm">
                {KEEP_WARM_MONTHS.map((m) => <option key={m} value={m}>{m} months</option>)}
              </select>
            </Field>
          )}
          <Field label="Reason (required)" htmlFor="stage-reason">
            <input id="stage-reason" required value={stageReason}
                   onChange={(e) => setStageReason(e.target.value)}
                   className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
          </Field>
          <button type="submit" disabled={busy !== null || !targetStage}
                  className="rounded bg-slate-900 px-3 py-1.5 text-xs font-medium text-white
                             disabled:opacity-50">
            {busy === 'stage' ? 'Moving…' : 'Move stage'}
          </button>
        </form>

        {/* -------- owner / next action -------- */}
        <form className="space-y-2 rounded border border-slate-200 p-3"
              onSubmit={(e) => {
                e.preventDefault()
                void run('workflow',
                  () => api.workflow(id, actor, workflowReason,
                    { owner, next_action: nextAction }),
                  'Owner and next action updated')
              }}>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Owner &amp; next action
          </h3>
          <Field label="Owner" htmlFor="owner-input">
            <input id="owner-input" value={owner} onChange={(e) => setOwner(e.target.value)}
                   className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
          </Field>
          <Field label="Next action" htmlFor="next-action-input">
            <input id="next-action-input" value={nextAction}
                   onChange={(e) => setNextAction(e.target.value)}
                   className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
          </Field>
          <Field label="Reason (required)" htmlFor="workflow-reason">
            <input id="workflow-reason" required value={workflowReason}
                   onChange={(e) => setWorkflowReason(e.target.value)}
                   className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
          </Field>
          <button type="submit" disabled={busy !== null}
                  className="rounded bg-slate-900 px-3 py-1.5 text-xs font-medium text-white
                             disabled:opacity-50">
            {busy === 'workflow' ? 'Saving…' : 'Update owner / next action'}
          </button>
        </form>

        {/* -------- note -------- */}
        <form className="space-y-2 rounded border border-slate-200 p-3"
              onSubmit={(e) => {
                e.preventDefault()
                void run('note', async () => {
                  await api.note(id, note, actor)
                  setNote('')
                }, 'Note appended')
              }}>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Add a note
          </h3>
          <Field label="Note" htmlFor="note-input" hint="Notes are append-only.">
            <textarea id="note-input" required value={note} rows={3}
                      onChange={(e) => setNote(e.target.value)}
                      className="mt-1 w-full rounded border border-slate-300 px-2 py-1
                                 text-sm" />
          </Field>
          <button type="submit" disabled={busy !== null}
                  className="rounded bg-slate-900 px-3 py-1.5 text-xs font-medium text-white
                             disabled:opacity-50">
            {busy === 'note' ? 'Saving…' : 'Append note'}
          </button>
          {wf && wf.notes.length > 0 && (
            <ul className="mt-2 space-y-1">
              {wf.notes.map((n, i) => (
                <li key={`${n.at}-${i}`} className="rounded bg-slate-50 p-2 text-xs">
                  <p className="text-slate-800">{n.text}</p>
                  <p className="text-[11px] text-slate-500">{n.actor}</p>
                </li>
              ))}
            </ul>
          )}
        </form>
      </div>
    </section>
  )
}
