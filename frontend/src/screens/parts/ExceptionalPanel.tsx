// C. Exceptional evidence — where F-13 lives.
//
// A detector CUE ("unusual evidence cue: exceptional progression — MEDIUM") is
// NOT the aggregated exceptional state. Two MEDIUM cues, or one STRONG cue,
// trigger the aggregate rule that floors attention at Priority Review; one
// MEDIUM cue does not. The panel therefore states the two facts separately and
// never says "this founder is exceptional".

import type { Assessment } from '../../types'
import { StrengthBadge } from '../../components/Badges'
import { signalLabel } from '../../vocab'

/**
 * Exceptional evidence. F-13: an individual detector CUE ("Exceptional
 * progression — Medium") is rendered separately from the AGGREGATED state
 * ("Priority override triggered: Yes/No"), because a single medium cue does not
 * mean the override fired. Not-fired detectors are shown too.
 */
export default function ExceptionalPanel({ assessment }: { assessment: Assessment }) {
  const { flag, rule, signals, not_fired: notFired } = assessment.exceptional
  return (
    <section aria-labelledby="exceptional-heading"
             className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="exceptional-heading" className="text-base font-semibold text-slate-900">
        Exceptional evidence
      </h2>

      <div className="mt-2 rounded-md border border-slate-300 bg-slate-50 p-3">
        <p className="text-sm">
          <span className="font-medium text-slate-800">Priority override triggered: </span>
          <span data-testid="exceptional-aggregate"
                className={flag ? 'font-semibold text-amber-800' : 'font-semibold text-slate-700'}>
            {flag ? 'Yes' : 'No'}
          </span>
        </p>
        <p className="mt-1 text-xs text-slate-600">{rule}</p>
        <p className="mt-1 text-[11px] text-slate-500">
          The aggregate rule fires on one STRONG cue or two MEDIUM cues. Individual cues below
          are observations, not the override.
        </p>
      </div>

      <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Unusual evidence cues {signals.length > 0 && `(${signals.length})`}
      </h3>
      {signals.length === 0 ? (
        <p className="mt-1 text-xs text-slate-500">No detector produced a cue.</p>
      ) : (
        <ul className="mt-1.5 space-y-1.5">
          {signals.map((s) => (
            <li key={s.name} data-testid={`cue-${s.name}`}
                className="rounded border border-slate-200 p-2 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-slate-800">{signalLabel(s.name)}</span>
                <StrengthBadge value={s.strength} />
                <span className="text-[11px] text-slate-500">unusual evidence cue</span>
              </div>
              <p className="mt-1 text-slate-700">{s.explanation}</p>
              {s.source_fields.length > 0 && (
                <p className="mt-1 break-all font-mono text-[11px] text-slate-500">
                  {s.source_fields.join(', ')}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      {Object.keys(notFired).length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-medium text-slate-600">
            Detectors that did not fire ({Object.keys(notFired).length}) — and why
          </summary>
          <ul className="mt-1.5 space-y-1 text-[11px] text-slate-600">
            {Object.entries(notFired).map(([name, why]) => (
              <li key={name}>
                <span className="font-medium">{signalLabel(name)}:</span> {why}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
