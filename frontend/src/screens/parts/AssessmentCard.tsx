// A. Machine assessment — the four orthogonal dimensions, each rendered as its
// own labelled thing, plus the freshness metadata.

import {
  ActionText, AttentionBadge, ConfidenceMeter, DataStateTag, PotentialChip,
} from '../../components/Badges'
import { Banner } from '../../components/States'
import type { Assessment, FounderDetail } from '../../types'
import { ACTION, ATTENTION, DATA_STATE, formatDateTime, POTENTIAL_SENTENCE } from '../../vocab'

/** One labelled dimension cell. */
function Cell({ label, help, children }:
  { label: string; help: string; children: React.ReactNode }) {
  return (
    <div className="min-w-[150px] flex-1 rounded-md border border-slate-200 bg-white p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <div className="mt-1.5">{children}</div>
      <p className="mt-1.5 text-[11px] leading-tight text-slate-500">{help}</p>
    </div>
  )
}

/**
 * The machine assessment: the four dimensions side by side, each in its own
 * visual form. Showing them together is the point — "Priority Review + Unknown
 * + Needs information" must read as a coherent sentence, not a contradiction.
 */
export default function AssessmentCard(
  { detail, effectiveRubric }: { detail: FounderDetail; effectiveRubric: string | null },
) {
  const a: Assessment = detail.assessment
  const meta = detail.assessment_metadata
  const stale = Boolean(effectiveRubric) && effectiveRubric !== meta.rubric_version

  return (
    <section aria-labelledby="assessment-heading"
             className="rounded-lg border border-slate-300 bg-slate-50 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="assessment-heading" className="text-base font-semibold text-slate-900">
          Machine assessment
        </h2>
        <p className="text-xs text-slate-500">
          Decision support — does not change workflow automatically.
        </p>
      </div>

      {stale && (
        <div className="mt-3">
          <Banner tone="warn">
            <strong>Assessment needs recalculation.</strong> This assessment was produced
            under rubric <code className="font-mono text-[11px]">
              {meta.rubric_version.slice(0, 12)}…</code>, and the effective configuration is
            now <code className="font-mono text-[11px]">
              {effectiveRubric?.slice(0, 12)}…</code>. Run <em>Recalculate assessments</em>
            from the config drawer on Pipeline &amp; Dashboard.
          </Banner>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-3">
        <Cell label="Attention" help={ATTENTION[a.attention].help}>
          <AttentionBadge value={a.attention} />
        </Cell>
        <Cell label="Potential" help={POTENTIAL_SENTENCE[a.potential]}>
          <PotentialChip value={a.potential} />
        </Cell>
        <Cell label="Evidence confidence"
              help="Coverage of decision-relevant evidence, less contradiction and inference
                    penalties. Not a quality score.">
          <ConfidenceMeter value={a.confidence} />
        </Cell>
        <Cell label="Data state" help={DATA_STATE[a.data_state].help}>
          <DataStateTag value={a.data_state} />
        </Cell>
        <Cell label="Recommended action" help={ACTION[a.recommended_action].help}>
          <ActionText value={a.recommended_action} />
        </Cell>
        <Cell label="Review priority score"
              help="Weighted evidence total (0–100). Never read it without the evidence
                    confidence beside it.">
          <span className="text-lg font-semibold tabular-nums text-slate-900">
            {a.broad_score.toFixed(1)}
          </span>
        </Cell>
        <Cell label="Archetype" help="A label for explanation. It feeds no number.">
          <span className="text-sm font-medium text-slate-800">{a.archetype.archetype}</span>
        </Cell>
        <Cell label="Exceptional evidence"
              help="The aggregated priority override — separate from individual cues below.">
          <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${
            a.exceptional.flag ? 'bg-amber-100 text-amber-900 ring-1 ring-amber-300'
              : 'bg-white text-slate-600 ring-1 ring-slate-300'}`}>
            {a.exceptional.flag ? 'Threshold met' : 'Threshold not met'}
          </span>
        </Cell>
      </div>

      <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-slate-500">
        <div className="flex gap-1">
          <dt>Assessment version</dt>
          <dd className="font-medium text-slate-700">v{meta.assessment_version}</dd>
        </div>
        <div className="flex gap-1">
          <dt>Assessed at</dt>
          <dd className="font-medium text-slate-700">{formatDateTime(meta.assessed_at)}</dd>
        </div>
        <div className="flex gap-1">
          <dt>Rubric</dt>
          <dd className="font-mono font-medium text-slate-700">
            {meta.rubric_version.slice(0, 12)}…
          </dd>
        </div>
        <div className="flex gap-1">
          <dt>Engine</dt>
          <dd className="font-medium text-slate-700">{meta.engine_version}</dd>
        </div>
      </dl>
    </section>
  )
}
