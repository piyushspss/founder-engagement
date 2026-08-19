// B. "Why this assessment?" — the policy trace and the signal table, with the
// provenance of every signal one click away.
//
// Zero-value signals are NOT hidden: "no explicit founder title observed" is an
// explanation, and removing it would make the score look like it came from
// nowhere.

import type { Assessment } from '../../types'
import { ProvenanceBadge, StrengthBadge } from '../../components/Badges'
import { signalLabel } from '../../vocab'

/**
 * The "why this assessment?" signal table: weight, value, weighted
 * contribution, strength, provenance type and source fields per signal.
 * Unobserved signals are shown as neutral defaults rather than hidden — a
 * missing signal must be visible as missing, not absent from the explanation.
 */
export default function SignalsTable(
  { assessment, weights }: { assessment: Assessment; weights: Record<string, number> | null },
) {
  const fired = assessment.policy_trace.filter((t) => t.fired)
  return (
    <section aria-labelledby="why-heading"
             className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="why-heading" className="text-base font-semibold text-slate-900">
        Why this assessment?
      </h2>

      <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Safety policy rules that fired
      </h3>
      <ul className="mt-1.5 space-y-1.5">
        {fired.map((t) => (
          <li key={t.rule} className="rounded border border-slate-200 bg-slate-50 p-2 text-xs">
            <p className="font-medium text-slate-800">{t.rule}</p>
            <p className="text-slate-600">{t.condition}</p>
            <p className="text-slate-500">{t.evidence}</p>
            {Object.keys(t.sets).length > 0 && (
              <p className="mt-0.5 text-slate-700">
                sets {Object.entries(t.sets).map(([k, v]) => `${k} = ${v}`).join(', ')}
              </p>
            )}
            {t.note && <p className="mt-0.5 italic text-slate-500">{t.note}</p>}
          </li>
        ))}
        {fired.length === 0 && <li className="text-xs text-slate-500">No rule fired.</li>}
      </ul>

      <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Deterministic signals
      </h3>
      <div className="mt-1.5 overflow-x-auto">
        <table className="w-full table-fixed text-left text-xs">
          <thead className="border-b border-slate-200 text-[11px] uppercase text-slate-500">
            <tr className="align-bottom">
              <th scope="col" className="w-[19%] py-1.5 pr-2">Signal</th>
              <th scope="col" className="w-[8%] py-1.5 pr-2">Weight</th>
              <th scope="col" className="w-[8%] py-1.5 pr-2">Value</th>
              <th scope="col" className="w-[10%] py-1.5 pr-2">Weighted</th>
              <th scope="col" className="w-[10%] py-1.5 pr-2">Strength</th>
              <th scope="col" className="w-[11%] py-1.5 pr-2">Prove&shy;nance</th>
              <th scope="col" className="w-[34%] py-1.5">Detail</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {assessment.signals.map((s) => {
              const weight = weights?.[s.name]
              return (
                <tr key={s.name} className={s.observed ? '' : 'text-slate-500'}>
                  <td className="py-1.5 pr-2 font-medium break-words">{signalLabel(s.name)}</td>
                  <td className="py-1.5 pr-2 tabular-nums">{weight ?? '—'}</td>
                  <td className="py-1.5 pr-2 tabular-nums">{s.value.toFixed(3)}</td>
                  <td className="py-1.5 pr-2 tabular-nums">
                    {weight === undefined ? '—' : (s.value * weight).toFixed(2)}
                  </td>
                  <td className="py-1.5 pr-2"><StrengthBadge value={s.strength} /></td>
                  <td className="py-1.5 pr-2"><ProvenanceBadge type={s.type} /></td>
                  <td className="py-1.5">
                    <details>
                      <summary className="cursor-pointer text-slate-600">
                        {s.observed ? 'sources & explanation' : 'not observed — why'}
                      </summary>
                      <p className="mt-1 max-w-prose text-slate-700">{s.explanation}</p>
                      {s.source_fields.length > 0 && (
                        <p className="mt-1 break-all font-mono text-[11px] text-slate-500">
                          {s.source_fields.join(', ')}
                        </p>
                      )}
                    </details>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
