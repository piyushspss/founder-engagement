// F. Normalized timeline. Anything the normalizer INFERRED is marked as
// inferred — a guessed month must never look like a read month.

import type { CanonicalRole, FounderDetail } from '../../types'

function monthYear(d: CanonicalRole['start_date']): string {
  if (!d) return '—'
  return `${String(d.month).padStart(2, '0')}/${d.year}`
}

/**
 * The normalized career timeline, showing what the normalizer read from the
 * raw record — including inferred months, so a filled gap is never displayed
 * as a supplied fact.
 */
export default function TimelinePanel({ detail }: { detail: FounderDetail }) {
  const roles = detail.facts.canonical.roles ?? []
  return (
    <section aria-labelledby="timeline-heading"
             className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="timeline-heading" className="text-base font-semibold text-slate-900">
        Normalized timeline
      </h2>
      <p className="mt-0.5 text-[11px] text-slate-500">
        Chronological order derived from the source record. Values marked
        <em className="not-italic font-medium"> inferred </em>
        were filled in by the normalizer, not read from the data.
      </p>

      {roles.length === 0 ? (
        <p className="mt-2 text-xs text-slate-500">No experience history recorded.</p>
      ) : (
        <ol className="mt-3 space-y-2">
          {roles.map((r) => {
            const flags = r.flags ?? []
            return (
              <li key={`${r.index}-${r.raw_index}`}
                  className="rounded border border-slate-200 p-2.5">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span className="text-sm font-medium text-slate-900">
                    {r.title ?? 'Title not recorded'}
                  </span>
                  <span className="text-sm text-slate-600">
                    {r.company ?? 'Company not recorded'}
                  </span>
                  {r.founder_title_flag === 'EXPLICIT' && (
                    <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[11px]
                                     font-medium text-emerald-900">
                      Explicit founder title
                    </span>
                  )}
                  {r.founder_title_flag === 'POSSIBLE' && (
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px]
                                     text-slate-700">
                      Possible founder title — not counted as evidence
                    </span>
                  )}
                  {r.health_flag === 'YES' && (
                    <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[11px] text-sky-900">
                      Healthcare
                    </span>
                  )}
                  {r.health_flag === 'UNKNOWN' && (
                    <span className="rounded bg-white px-1.5 py-0.5 text-[11px] text-slate-600
                                     ring-1 ring-slate-300">
                      Industry unknown — neither health nor non-health
                    </span>
                  )}
                </div>

                <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px]
                                text-slate-600">
                  <span>
                    {monthYear(r.start_date)} → {r.is_current === 'YES' ? 'present'
                      : monthYear(r.end_date)}
                    {r.start_date?.inferred_month && (
                      <em className="ml-1 not-italic text-amber-700">(start month inferred)</em>
                    )}
                    {r.end_date?.inferred_month && (
                      <em className="ml-1 not-italic text-amber-700">(end month inferred)</em>
                    )}
                  </span>
                  <span>Current: {r.is_current}</span>
                  {r.duration_months != null && <span>{r.duration_months} months</span>}
                  {r.management_level && <span>Level: {r.management_level}</span>}
                  {r.company_size != null && <span>{r.company_size} employees</span>}
                  {r.industry && <span>{r.industry}</span>}
                </div>

                {flags.length > 0 && (
                  <ul className="mt-1.5 flex flex-wrap gap-1">
                    {flags.map((f, i) => (
                      <li key={`${f.code}-${i}`}
                          title={f.detail}
                          className={`rounded px-1.5 py-0.5 text-[11px] ${
                            f.kind === 'CONTRADICTION'
                              ? 'bg-rose-50 text-rose-900 ring-1 ring-rose-200'
                              : f.kind === 'INFERENCE'
                                ? 'bg-amber-50 text-amber-900 ring-1 ring-amber-200'
                                : 'bg-slate-50 text-slate-700 ring-1 ring-slate-200'}`}>
                        {f.kind.toLowerCase()}: {f.code}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
