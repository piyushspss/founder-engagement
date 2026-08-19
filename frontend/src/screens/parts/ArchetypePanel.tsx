// D. Archetype — a LABEL, not a rank. Secondary matches stay visible.

import type { Assessment } from '../../types'
import { signalLabel } from '../../vocab'

/**
 * The archetype label plus what is conspicuously missing for it. A LABEL only —
 * it changes no score and no dimension. "Insufficient Evidence" is the fallback
 * for a profile that matched none of the eight archetypes, not a ninth one.
 */
export default function ArchetypePanel({ assessment }: { assessment: Assessment }) {
  const a = assessment.archetype
  return (
    <section aria-labelledby="archetype-heading"
             className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="archetype-heading" className="text-base font-semibold text-slate-900">
        Archetype
      </h2>
      <p className="mt-0.5 text-[11px] text-slate-500">
        A descriptive label used for explanation and for knowing what to go and look for.
        It is not a score and not a ranking.
      </p>

      <p className="mt-2">
        <span className="rounded-md bg-slate-900 px-2 py-1 text-sm font-medium text-white">
          {a.archetype}
        </span>
      </p>
      {a.explanation && <p className="mt-2 text-xs text-slate-700">{a.explanation}</p>}

      {a.secondary.length > 0 && (
        <div className="mt-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Also matches
          </h3>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {a.secondary.map((s) => (
              <li key={s}
                  className="rounded border border-slate-300 px-2 py-0.5 text-xs text-slate-700">
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {a.strong_signals.length > 0 && (
        <div className="mt-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Evidence behind the label
          </h3>
          <ul className="mt-1 list-disc pl-5 text-xs text-slate-700">
            {a.strong_signals.map((s) => <li key={s}>{signalLabel(s)}</li>)}
          </ul>
        </div>
      )}

      {a.missing_for_archetype.length > 0 && (
        <div className="mt-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            What is missing for this archetype
          </h3>
          <ul className="mt-1 list-disc pl-5 text-xs text-slate-700">
            {a.missing_for_archetype.map((s) => <li key={s}>{signalLabel(s)}</li>)}
          </ul>
        </div>
      )}
    </section>
  )
}
