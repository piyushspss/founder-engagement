// The four orthogonal dimensions, rendered as four visually DIFFERENT things:
//
//   attention   filled pill with a leading bar
//   potential   outlined chip (dashed outline when the judgment was not made)
//   confidence  a labelled meter, never a colour-only badge
//   data state  square-cornered tag
//
// Collapsing them into one coloured badge would destroy the product's whole
// point: "Priority Review + Unknown" has to read as a coherent sentence, not a
// contradiction. Every badge carries TEXT — colour never carries meaning alone.

import type { Attention, DataState, Potential, RecommendedAction } from '../types'
import { ACTION, ATTENTION, DATA_STATE, POTENTIAL, PROVENANCE } from '../vocab'

/**
 * Attention as a filled pill. Never rendered as a quality/severity colour:
 * ROUTINE is "nothing here needs a human today", not "this founder is weak".
 */
export function AttentionBadge({ value }: { value: Attention }) {
  const meta = ATTENTION[value]
  return (
    <span
      title={meta.help}
      data-testid={`attention-${value}`}
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs
                  font-semibold whitespace-nowrap ${meta.className}`}
    >
      <span aria-hidden className="h-3 w-1 rounded-sm bg-current opacity-70" />
      {meta.label}
    </span>
  )
}

/**
 * Potential as an OUTLINED chip — deliberately a different shape from attention.
 * F-9: UNKNOWN gets a dashed outline and its own copy ("insufficient evidence
 * to judge"), is never red, and is never ranked below LOW. LOW is a conclusion
 * the system earned; UNKNOWN is one it declined to draw.
 */
export function PotentialChip({ value, withHint = false }:
  { value: Potential; withHint?: boolean }) {
  const meta = POTENTIAL[value]
  return (
    <span className="inline-flex flex-col items-start gap-0.5">
      <span
        title={meta.help}
        data-testid={`potential-${value}`}
        data-potential={value}
        className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium
                    whitespace-nowrap ${meta.className}`}
      >
        {meta.label}
      </span>
      {withHint && (
        <span className="text-[11px] leading-tight text-slate-500">{meta.help}</span>
      )}
    </span>
  )
}

/**
 * Evidence confidence as a labelled meter. Always shows the number — colour
 * alone never carries meaning. Confidence is about the EVIDENCE, not the person.
 */
export function ConfidenceMeter({ value, compact = false }:
  { value: number; compact?: boolean }) {
  const pct = Math.round((value ?? 0) * 100)
  return (
    <span className="inline-flex items-center gap-2" title="Evidence confidence — how well
      covered the decision-relevant evidence is. Not a quality score.">
      <span
        role="meter"
        aria-label="Evidence confidence"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        className="relative block h-1.5 w-16 overflow-hidden rounded-full bg-slate-200"
      >
        <span className="absolute inset-y-0 left-0 rounded-full bg-slate-500"
              style={{ width: `${pct}%` }} />
      </span>
      <span className="tabular-nums text-xs text-slate-700">{value?.toFixed(2)}</span>
      {!compact && <span className="sr-only">evidence confidence</span>}
    </span>
  )
}

/** Data state as a square-cornered tag — the fourth distinct visual form. */
export function DataStateTag({ value }: { value: DataState }) {
  const meta = DATA_STATE[value]
  return (
    <span
      title={meta.help}
      data-testid={`data-state-${value}`}
      className={`inline-flex items-center rounded-sm px-2 py-0.5 text-xs whitespace-nowrap
                  ${meta.className}`}
    >
      {meta.label}
    </span>
  )
}

/** The recommended action, as advisory text rather than a badge — it is a
 *  suggestion to a reviewer, never a decision. */
export function ActionText({ value }: { value: RecommendedAction }) {
  const meta = ACTION[value]
  return (
    <span title={meta.help} className={`text-xs font-medium ${meta.className}`}>
      {meta.label}
    </span>
  )
}

/**
 * Provenance type of a signal. `AI_INTERPRETED` is styled distinctly from
 * OBSERVED/DERIVED so an AI reading can never be misread as an observed fact.
 */
export function ProvenanceBadge({ type }: { type: string }) {
  const meta = PROVENANCE[type] ?? { label: type, help: type, className: 'bg-slate-100' }
  return (
    <span title={meta.help}
          className={`inline-flex rounded px-1.5 py-0.5 text-[11px] ${meta.className}`}>
      {meta.label}
    </span>
  )
}

/** Signal strength. NONE means "not observed", not "observed and weak". */
export function StrengthBadge({ value }: { value: string }) {
  const tone = value === 'STRONG' ? 'bg-slate-800 text-white'
    : value === 'MEDIUM' ? 'bg-slate-300 text-slate-900'
      : value === 'WEAK' ? 'bg-slate-100 text-slate-700 ring-1 ring-slate-300'
        : 'bg-white text-slate-500 ring-1 ring-slate-200'
  return (
    <span className={`inline-flex rounded px-1.5 py-0.5 text-[11px] font-medium ${tone}`}>
      {value.charAt(0) + value.slice(1).toLowerCase()}
    </span>
  )
}

/**
 * A WORKFLOW obligation — a commitment a person made, now coming round. It is
 * shaped and worded to be unmistakable from a machine dimension: an outlined
 * amber tag with a clock glyph, never a filled attention pill. A founder whose
 * machine attention is Routine can carry this badge, and that is not a
 * contradiction.
 */
export function WorkflowReasonBadge({ reason }: { reason: string }) {
  const inconsistent = reason.toLowerCase().includes('inconsistent')
  return (
    <span
      data-testid={inconsistent ? 'workflow-inconsistent' : 'workflow-due'}
      title={inconsistent
        ? 'This founder is in Keep warm with no re-engagement date. Reported as '
          + 'inconsistent data — the system will not guess a date, and will not '
          + 'surface them as due.'
        : 'A human set a keep-warm date and that date has arrived. The machine '
          + 'assessment has not changed.'}
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs
                  font-medium whitespace-nowrap ${
        inconsistent
          ? 'border-rose-400 bg-white text-rose-800'
          : 'border-amber-500 bg-white text-amber-900'}`}
    >
      <span aria-hidden>{inconsistent ? '!' : '\u23F1'}</span>
      {reason}
    </span>
  )
}
