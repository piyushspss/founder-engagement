// E. Missing evidence, contradictions and duplicates.
//
// Neutral, factual language throughout. A contradiction is a reason evidence
// confidence falls — never an accusation that the person or the source lied.

import type { FounderDetail } from '../../types'

/** One titled group of uncertainty items. */
function Group({ title, hint, items }:
  { title: string; hint: string; items: { key: string; head: string; body: string;
                                          sources?: string[] }[] }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title} ({items.length})
      </h3>
      <p className="text-[11px] text-slate-500">{hint}</p>
      {items.length === 0 ? (
        <p className="mt-1 text-xs text-slate-500">None recorded.</p>
      ) : (
        <ul className="mt-1.5 space-y-1">
          {items.map((i) => (
            <li key={i.key} className="rounded border border-slate-200 p-2 text-xs">
              <p className="font-mono text-[11px] text-slate-500">{i.head}</p>
              <p className="text-slate-800">{i.body}</p>
              {i.sources && i.sources.length > 0 && (
                <p className="mt-0.5 break-all font-mono text-[11px] text-slate-500">
                  {i.sources.join(', ')}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * Missing data, contradictions and duplicates — surfaced as things to go and
 * FIND, never as marks against the founder. Missing data cost confidence, not
 * score. Duplicates are flagged for a human and never auto-merged (A6b).
 */
export default function UncertaintyPanel({ detail }: { detail: FounderDetail }) {
  const a = detail.assessment
  const links = detail.duplicates.links as Record<string, unknown>[]
  return (
    <section aria-labelledby="uncertainty-heading"
             className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="uncertainty-heading" className="text-base font-semibold text-slate-900">
        Missing evidence, contradictions &amp; duplicates
      </h2>
      <p className="mt-0.5 text-[11px] text-slate-500">
        Missing data is reported, never scored as negative evidence. It lowers evidence
        confidence and raises review pressure.
      </p>

      <div className="mt-3 grid gap-4 md:grid-cols-3">
        <Group title="Missing" hint="Things to go and find."
               items={a.missing.map((m) => ({ key: m.code, head: m.code, body: m.detail,
                                              sources: m.source_fields }))} />
        <Group title="Contradictions" hint="The record disagrees with itself."
               items={a.contradictions.map((c) => ({ key: c.code + c.detail, head: c.code,
                                                     body: c.detail,
                                                     sources: c.source_fields }))} />
        <Group title="Possible duplicates"
               hint="Flagged for a person to judge. Nothing is ever merged automatically."
               items={links.map((l, i) => ({
                 key: `${l.other_person_id}-${i}`,
                 head: String(l.relation),
                 body: `Shares ${(l.matching_hashes as string[] ?? []).join(', ') || '—'} with `
                     + `${l.other_person_id}`
                     + ((l.conflicting_hashes as string[] ?? []).length
                       ? `; conflicting: ${(l.conflicting_hashes as string[]).join(', ')}`
                       : ''),
               }))} />
      </div>

      <details className="mt-3">
        <summary className="cursor-pointer text-xs font-medium text-slate-600">
          Evidence confidence breakdown
        </summary>
        <div className="mt-1.5 overflow-x-auto">
          <table className="min-w-[420px] text-left text-xs">
            <thead className="text-[11px] uppercase text-slate-500">
              <tr><th className="py-1 pr-4">Coverage component</th><th className="py-1">Value</th></tr>
            </thead>
            <tbody>
              {Object.entries(a.confidence_breakdown.coverage_components ?? {}).map(([k, v]) => (
                <tr key={k} className="border-t border-slate-100">
                  <td className="py-1 pr-4 text-slate-700">{k.replace(/_/g, ' ')}</td>
                  <td className="py-1 tabular-nums">{Number(v).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  )
}
