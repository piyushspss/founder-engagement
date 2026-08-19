// The optional AI evidence overlay.
//
// Deliberately subordinate: it sits BELOW the machine assessment, in a lighter
// frame, and it never replaces the assessment card with a generated summary.
// The wording rules are the product's, not a style preference — this layer
// identifies unusual supplied evidence that the deterministic rubric may
// underrepresent. It does not recommend a founder, predict success, approve or
// reject anyone, and it can only ever RAISE attention.

import { useState } from 'react'
import { api } from '../../api'
import { ErrorBox } from '../../components/States'
import { ProvenanceBadge, StrengthBadge } from '../../components/Badges'
import type { AICheckResponse, AILayerStatus } from '../../types'
import { formatDateTime, signalLabel } from '../../vocab'

/**
 * The three AI states are labelled DIFFERENTLY on purpose: unavailable / Mock /
 * Run. A mock result is never presented as a real model result, and an absent
 * provider is never silently substituted with the mock.
 */
function providerLabel(status: AILayerStatus | null): string {
  if (!status || !status.available) return 'AI evidence check unavailable'
  return status.provider === 'mock' ? 'Mock AI evidence check' : 'Run AI evidence check'
}

/**
 * The optional AI overlay panel. Runs ONLY when the button is pressed — never
 * on mount, never on load — so cost, latency and human intent stay visible.
 * Renders accepted cues, discarded items WITH their reasons, and unsupported
 * inferences as diagnostics. The result is component state and is discarded on
 * unmount: nothing here is persisted.
 */
export default function AIEvidencePanel(
  { founderId, status }: { founderId: string; status: AILayerStatus | null },
) {
  const [result, setResult] = useState<AICheckResponse | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  const unavailable = !status || !status.available
  const isMock = result ? result.provider === 'mock' : status?.provider === 'mock'

  const run = async () => {
    setBusy(true); setError(null)
    try {
      setResult(await api.aiCheck(founderId))
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="ai-heading"
             data-testid="ai-evidence-panel"
             className="rounded-lg border border-dashed border-violet-300 bg-violet-50/40 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="ai-heading" className="text-sm font-semibold text-violet-900">
          AI-interpreted evidence — supplemental
        </h2>
        <p className="text-[11px] text-violet-900/70">
          Optional. Identifies unusual supplied evidence the rubric may underrepresent.
          It may only raise attention, never lower it, and it changes no assessment,
          decision or workflow.
        </p>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" data-testid="ai-check-button"
                onClick={() => void run()} disabled={unavailable || busy}
                title={unavailable ? (status?.detail ?? 'no AI provider is configured')
                  : undefined}
                className={`rounded px-3 py-1.5 text-xs font-medium ${
                  unavailable ? 'cursor-not-allowed border border-slate-300 bg-slate-100 '
                    + 'text-slate-500'
                    : 'bg-violet-800 text-white'}`}>
          {busy ? 'Checking…' : providerLabel(status)}
        </button>
        {isMock && (
          <span data-testid="ai-mock-label"
                className="rounded border border-violet-400 px-2 py-0.5 text-[11px]
                           font-medium text-violet-900">
            Mock adapter — canned output, not a model result
          </span>
        )}
        {unavailable && (
          <span className="text-[11px] text-slate-600">
            {status?.detail ?? 'no AI provider is configured'} — the deterministic
            assessment is unaffected.
          </span>
        )}
      </div>

      {error != null && <div className="mt-3"><ErrorBox error={error} /></div>}

      {result && (
        <div className="mt-3 space-y-3">
          {result.status !== 'ok' && (
            <p role="status" className="rounded border border-slate-300 bg-white px-2.5
                                        py-1.5 text-xs text-slate-700">
              {result.status === 'unavailable' && 'AI evidence check unavailable. '}
              {result.status === 'error' && 'The provider call failed. '}
              {result.status === 'malformed' && 'The provider returned output that failed '
                + 'validation, so no evidence was accepted. '}
              {result.detail} The deterministic assessment is unchanged.
            </p>
          )}

          <p className="text-xs text-slate-800" data-testid="ai-attention">
            {result.attention_changed
              ? <>Attention raised from <strong>{result.attention_before}</strong> to{' '}
                <strong>{result.attention_with_ai}</strong> by supplemental evidence.</>
              : <>Attention unchanged: <strong>{result.attention_before}</strong>.</>}
            {' '}<span className="text-slate-500">{result.attention_change_reason}</span>
          </p>

          {result.ai_evidence.length > 0 ? (
            <ul className="space-y-2">
              {result.ai_evidence.map((cue, i) => (
                <li key={`${cue.category}-${i}`}
                    className="rounded border border-violet-200 bg-white p-2.5 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-slate-900">
                      {signalLabel(cue.category)}
                    </span>
                    <StrengthBadge value={cue.strength} />
                    <ProvenanceBadge type={cue.signal.type} />
                    <span className="text-[11px] text-slate-500">
                      unusual evidence cue
                    </span>
                  </div>
                  <p className="mt-1 text-slate-800">{cue.claim}</p>
                  <p className="mt-1 break-all font-mono text-[11px] text-slate-500">
                    {cue.source_fields.join(', ')}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    {cue.metadata.provider} · {cue.metadata.model} ·
                    {' '}prompt {cue.metadata.prompt_version}
                    {' '}({cue.metadata.prompt_sha256.slice(0, 12)}…) ·
                    {' '}{formatDateTime(cue.metadata.generated_at)}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-slate-600">No supplemental evidence accepted.</p>
          )}

          {result.discarded_evidence.length > 0 && (
            <details className="rounded border border-slate-200 bg-white p-2">
              <summary className="cursor-pointer text-xs font-medium text-slate-700">
                Discarded — failed provenance validation
                ({result.discarded_evidence.length})
              </summary>
              <ul className="mt-1.5 space-y-1 text-[11px] text-slate-700">
                {result.discarded_evidence.map((d, i) => (
                  <li key={i} className="rounded bg-slate-50 p-1.5">
                    <p>{d.claim}</p>
                    <p className="text-slate-500">{d.reason}: {d.detail}</p>
                  </li>
                ))}
              </ul>
            </details>
          )}

          {result.unsupported_inferences.length > 0 && (
            <details className="rounded border border-slate-200 bg-white p-2">
              <summary className="cursor-pointer text-xs font-medium text-slate-700">
                Unsupported inferences — diagnostic only, never evidence
                ({result.unsupported_inferences.length})
              </summary>
              <ul className="mt-1.5 list-disc pl-5 text-[11px] text-slate-700">
                {result.unsupported_inferences.map((u) => <li key={u}>{u}</li>)}
              </ul>
            </details>
          )}
        </div>
      )}
    </section>
  )
}
