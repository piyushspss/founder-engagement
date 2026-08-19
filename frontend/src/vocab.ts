// The presentation vocabulary. One place, because the wording of these four
// dimensions IS the product's safety story.
//
// Two rules encoded here and pinned by tests:
//
//   F-9  UNKNOWN is an UNMADE JUDGMENT, not a bad score. It is never red, never
//        "poor", never ranked below LOW on a quality scale. LOW is a conclusion
//        the system earned the right to draw; UNKNOWN is a conclusion it
//        declined to draw.
//   F-13 A MEDIUM exceptional detector CUE is not the aggregated
//        `exceptional = true` state. The two are rendered separately, always.

import type {
  Attention, DataState, Disposition, Potential, RecommendedAction, Stage,
} from './types'

export interface Meta {
  label: string
  help: string
  className: string
}

/** Attention — how urgently a human must look. Filled pill. */
export const ATTENTION: Record<Attention, Meta> = {
  PRIORITY_REVIEW: {
    label: 'Priority Review',
    help: 'Look at this first. Either exceptional evidence or strong, well-covered evidence.',
    className: 'bg-amber-100 text-amber-900 ring-1 ring-amber-300',
  },
  REVIEW: {
    label: 'Review',
    help: 'A person should read this before it moves on.',
    className: 'bg-sky-100 text-sky-900 ring-1 ring-sky-300',
  },
  ROUTINE: {
    label: 'Routine',
    help: 'Sufficient evidence to be comfortable not prioritising this now. Still visible, '
        + 'never hidden.',
    className: 'bg-slate-100 text-slate-700 ring-1 ring-slate-300',
  },
}

/**
 * Potential — the strength of the founder-quality claim.
 * Outlined chip (a different SHAPE from attention, so the two dimensions cannot
 * be read as one badge).
 */
export const POTENTIAL: Record<Potential, Meta> = {
  HIGH: {
    label: 'High',
    help: 'High — strong evidence, sufficiently covered.',
    className: 'border border-emerald-400 text-emerald-800 bg-white',
  },
  MEDIUM: {
    label: 'Medium',
    help: 'Medium — mixed or moderate positive evidence.',
    className: 'border border-sky-400 text-sky-800 bg-white',
  },
  LOW: {
    label: 'Low',
    help: 'Low — sufficient evidence, limited positive signals.',
    className: 'border border-slate-400 text-slate-700 bg-white',
  },
  UNKNOWN: {
    label: 'Unknown',
    help: 'Unknown — insufficient evidence to judge. Not a low score: the system '
        + 'declined to make the claim.',
    className: 'border border-dashed border-violet-400 text-violet-800 bg-white',
  },
}

/** Longer copy used on the detail screen and in tooltips. */
export const POTENTIAL_SENTENCE: Record<Potential, string> = {
  HIGH: 'High — sufficient evidence, strong positive signals.',
  MEDIUM: 'Medium — sufficient evidence, moderate positive signals.',
  LOW: 'Low — sufficient evidence, limited positive signals.',
  UNKNOWN: 'Unknown — insufficient evidence to judge.',
}

/** Data state — whether we hold enough to decide at all. Square tag. */
export const DATA_STATE: Record<DataState, Meta> = {
  SUFFICIENT: {
    label: 'Sufficient',
    help: 'Decision-relevant evidence is adequately covered.',
    className: 'bg-white text-slate-700 ring-1 ring-slate-300',
  },
  PARTIAL: {
    label: 'Partial',
    help: 'Some decision-relevant evidence is missing. Attention is floored at Review.',
    className: 'bg-white text-indigo-800 ring-1 ring-indigo-300',
  },
  NEEDS_INFORMATION: {
    label: 'Needs information',
    help: 'Experience history is missing or incomplete. Someone needs to go and find it.',
    className: 'bg-white text-indigo-900 ring-1 ring-indigo-400 font-medium',
  },
}

/** Recommended action — ADVISORY. Rendered as text, never as an action button:
 *  the machine recommends, a person decides. */
export const ACTION: Record<RecommendedAction, Meta> = {
  CONSIDER_ENGAGEMENT: {
    label: 'Consider engagement',
    help: 'Suggested next step for a person. Never executed automatically.',
    className: 'text-emerald-800',
  },
  HUMAN_REVIEW: { label: 'Human review', help: 'A person should read the evidence.',
    className: 'text-sky-800' },
  RESEARCH: { label: 'Needs research', help: 'Go and find the missing evidence.',
    className: 'text-indigo-800' },
  NO_URGENT_ACTION: { label: 'No urgent action', help: 'Nothing needed right now.',
    className: 'text-slate-600' },
}

/** Human lifecycle stage labels. */
export const STAGE_LABEL: Record<Stage, string> = {
  NEW: 'New', ASSESSMENT: 'Assessment', POTENTIAL: 'Potential', NURTURING: 'Nurturing',
  KEEP_WARM: 'Keep warm', DEAL: 'Deal', CLOSED: 'Closed',
}

/** Kanban column order — display only, NOT the legal transition map (which is
 *  server-side and enforced there). */
export const STAGE_ORDER: Stage[] = [
  'NEW', 'ASSESSMENT', 'POTENTIAL', 'NURTURING', 'KEEP_WARM', 'DEAL', 'CLOSED',
]

/** Human disposition labels. Disposition is a human act; the machine has no
 *  vocabulary for these values. */
export const DISPOSITION_LABEL: Record<Disposition, string> = {
  NEEDS_REVIEW: 'Needs review',
  POTENTIAL: 'Potential',
  NOT_NOW: 'Not now',
  NEEDS_INFORMATION: 'Needs information',
}

/** Reviewer-facing names for backend signal keys. */
export const SIGNAL_LABEL: Record<string, string> = {
  founder_evidence: 'Founder evidence',
  healthcare_depth: 'Healthcare depth',
  leadership: 'Leadership',
  career_trajectory: 'Career trajectory',
  education_signal: 'Education signal',
  operating_environment: 'Operating environment',
  technical_evidence: 'Technical evidence',
  exceptional_signals: 'Exceptional signals',
}

/** A signal's label, falling back to a humanised key for anything unmapped —
 *  an unknown signal is still shown, never silently dropped. */
export function signalLabel(name: string): string {
  return SIGNAL_LABEL[name] ?? name.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())
}

/** Provenance styling. AI_INTERPRETED is visually distinct and its help text
 *  states the raise-only limit, so the AI layer's authority is legible in the UI. */
export const PROVENANCE: Record<string, { label: string; help: string; className: string }> = {
  OBSERVED: { label: 'Observed', help: 'Read directly from a source field.',
    className: 'bg-slate-100 text-slate-700' },
  DERIVED: { label: 'Derived', help: 'Computed by a rule from observed fields.',
    className: 'bg-slate-100 text-slate-700 italic' },
  AI_INTERPRETED: { label: 'AI', help: 'Suggested by the optional AI evidence layer. '
    + 'May only raise attention.', className: 'bg-violet-100 text-violet-800' },
}

/**
 * Turn one backend `why_surfaced` entry into reviewer-facing copy.
 * This RE-WORDS what the backend decided; it never re-derives policy.
 */
export function formatWhy(entry: string): string {
  if (entry === 'Re-engagement due') return 'Re-engagement due'
  if (entry.startsWith('Exceptional evidence:')) {
    return `Exceptional evidence threshold met — ${entry.slice('Exceptional evidence:'.length).trim()}`
  }
  if (entry.startsWith('Data state ')) {
    const state = entry.slice('Data state '.length) as DataState
    return state === 'NEEDS_INFORMATION'
      ? 'Experience history incomplete — needs research'
      : 'Evidence incomplete — human review needed'
  }
  const match = /^(\w+) (STRONG|MEDIUM|WEAK|NONE)$/.exec(entry)
  if (match) {
    return `${signalLabel(match[1])} — ${match[2].toLowerCase()}`
  }
  return entry
}

/** Format a UTC timestamp for display. Backend values are UTC; a bare string
 *  is suffixed with `Z` so it is never parsed as local time. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value.endsWith('Z') ? value : `${value}Z`)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

/** Format a UTC date. Parsed at UTC midnight so a keep-warm due date never
 *  shifts a day under a negative-offset timezone. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(`${value}T00:00:00Z`)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleDateString(undefined, { dateStyle: 'medium' })
}

/** Truncate a founder id for table display. */
export function shortId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 8)}…` : id
}
