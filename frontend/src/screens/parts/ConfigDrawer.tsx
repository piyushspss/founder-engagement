// The config drawer — weights, thresholds and tier lists are CONFIG, not code.
//
// Two things this drawer must never do: rescore on save, and imply that a list
// edit is additive. `PUT /config` REPLACES a list wholesale, so the drawer edits
// and submits the complete intended list, and says so on screen.

import { useEffect, useState } from 'react'
import { api } from '../../api'
import { Banner, ErrorBox } from '../../components/States'
import type { EffectiveConfig } from '../../types'

interface Props {
  open: boolean
  onClose: () => void
  config: EffectiveConfig
  actor: string
  onSaved: () => void
  onRescored: () => void
}

const lines = (list: string[]) => list.join('\n')
const parseLines = (text: string) =>
  text.split('\n').map((s) => s.trim()).filter(Boolean)

/**
 * Live editor for weights, thresholds, tier lists and the health taxonomy —
 * these are CONFIG, not code.
 *
 * Saving persists the config and explicitly DOES NOT rescore; rescoring is a
 * separate deliberate act, so a config change never silently rewrites the
 * assessments a reviewer has been working from.
 */
export default function ConfigDrawer(
  { open, onClose, config, actor, onSaved, onRescored }: Props,
) {
  const c = config.config
  const [thresholds, setThresholds] = useState<Record<string, string>>({})
  const [weights, setWeights] = useState<Record<string, string>>({})
  const [instTier1, setInstTier1] = useState('')
  const [instTier2, setInstTier2] = useState('')
  const [healthTier1, setHealthTier1] = useState('')
  const [healthIndustries, setHealthIndustries] = useState('')

  const [saving, setSaving] = useState(false)
  const [rescoring, setRescoring] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [savedHash, setSavedHash] = useState<string | null>(null)
  const [rescoreResult, setRescoreResult] = useState<string | null>(null)

  useEffect(() => {
    setThresholds(Object.fromEntries(
      Object.entries(c.weights.thresholds).map(([k, v]) => [k, String(v)])))
    setWeights(Object.fromEntries(
      Object.entries(c.weights.signal_weights).map(([k, v]) => [k, String(v)])))
    setInstTier1(lines(c.institutions.tier_1))
    setInstTier2(lines(c.institutions.tier_2))
    setHealthTier1(lines(c.health.tier_1))
    setHealthIndustries(lines(c.health.health_industries))
  }, [config])

  if (!open) return null

  const save = async () => {
    setSaving(true); setError(null); setRescoreResult(null)
    try {
      const payload = {
        weights: {
          thresholds: Object.fromEntries(
            Object.entries(thresholds).map(([k, v]) => [k, Number(v)])),
          signal_weights: Object.fromEntries(
            Object.entries(weights).map(([k, v]) => [k, Number(v)])),
        },
        institutions: { tier_1: parseLines(instTier1), tier_2: parseLines(instTier2) },
        health: { tier_1: parseLines(healthTier1),
                  health_industries: parseLines(healthIndustries) },
      }
      const result = await api.putConfig(payload, actor)
      setSavedHash(result.rubric_version)
      onSaved()
    } catch (e) {
      setError(e)
    } finally {
      setSaving(false)
    }
  }

  const recalculate = async () => {
    setRescoring(true); setError(null)
    try {
      const result = await api.rescore(actor, 'config change applied from the config drawer')
      // F-18: `assessments_changed` counts records REWRITTEN under the new
      // rubric, not founders whose conclusion moved. The copy must not overstate it.
      setRescoreResult(
        `Recalculated ${result.founders_rescored} founders. `
        + `${result.assessments_changed} assessments re-evaluated and rewritten `
        + `(this counts records rewritten under the new rubric, not founders whose `
        + `conclusion changed). `
        + `${result.canonical_profiles_changed} normalized profiles changed. `
        + `Human decisions and workflow untouched: ${!result.human_state_touched}. `
        + `New rubric ${result.rubric_version.slice(0, 12)}…`)
      setSavedHash(null)
      onRescored()
    } catch (e) {
      setError(e)
    } finally {
      setRescoring(false)
    }
  }

  const numberGrid = (values: Record<string, string>,
                      set: (v: Record<string, string>) => void, prefix: string) => (
    <div className="grid grid-cols-2 gap-2">
      {Object.entries(values).map(([key, value]) => (
        <div key={key}>
          <label htmlFor={`${prefix}-${key}`}
                 className="block text-[11px] font-medium text-slate-600">
            {key.replace(/_/g, ' ')}
          </label>
          <input id={`${prefix}-${key}`} type="number" step="any" value={value}
                 onChange={(e) => set({ ...values, [key]: e.target.value })}
                 className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
        </div>
      ))}
    </div>
  )

  const listField = (id: string, label: string, value: string,
                     set: (v: string) => void) => (
    <div>
      <label htmlFor={id} className="block text-[11px] font-medium text-slate-600">
        {label} <span className="font-normal text-slate-400">(one per line)</span>
      </label>
      <textarea id={id} value={value} onChange={(e) => set(e.target.value)} rows={6}
                className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1
                           font-mono text-[11px]" />
      <p className="text-[11px] text-slate-500">
        {parseLines(value).length} entries — saving replaces the whole list.
      </p>
    </div>
  )

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <button type="button" aria-label="Close configuration"
              onClick={onClose} className="flex-1 bg-slate-900/30" />
      <aside role="dialog" aria-modal="true" aria-labelledby="config-heading"
             className="h-full w-full max-w-xl overflow-y-auto border-l border-slate-300
                        bg-white p-4 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id="config-heading" className="text-base font-semibold text-slate-900">
              Configuration
            </h2>
            <p className="mt-0.5 font-mono text-[11px] text-slate-500">
              effective rubric {config.rubric_version.slice(0, 16)}…
            </p>
          </div>
          <button type="button" onClick={onClose}
                  className="rounded border border-slate-300 px-2 py-1 text-xs">
            Close
          </button>
        </div>

        <div className="mt-3 space-y-2">
          <Banner tone="info">
            Changing configuration does not automatically change human decisions or workflow,
            and does not recalculate anything. Assessments keep the rubric they were produced
            under until you explicitly recalculate.
          </Banner>
          <Banner tone="warn">
            <strong>List fields are replaced, not merged.</strong> Whatever is in a list box
            when you save becomes the entire list. Remove a line to remove that entry.
          </Banner>
        </div>

        {error != null && <div className="mt-3"><ErrorBox error={error} /></div>}

        {savedHash && (
          <div className="mt-3 space-y-2">
            <Banner tone="warn">
              Saved. Stored assessments are now based on an <strong>older rubric</strong> than
              the effective configuration
              (<code className="font-mono">{savedHash.slice(0, 12)}…</code>).
              Recalculate to bring them up to date.
            </Banner>
            <button type="button" onClick={() => void recalculate()} disabled={rescoring}
                    className="rounded bg-slate-900 px-3 py-1.5 text-xs font-medium text-white
                               disabled:opacity-50">
              {rescoring ? 'Recalculating…' : 'Recalculate assessments'}
            </button>
          </div>
        )}

        {rescoreResult && (
          <div className="mt-3"><Banner tone="ok">{rescoreResult}</Banner></div>
        )}

        <section className="mt-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Thresholds
          </h3>
          <p className="mb-1.5 text-[11px] text-slate-500">
            Operating hypotheses tuned to review capacity, not learned from outcomes.
          </p>
          {numberGrid(thresholds, setThresholds, 'threshold')}
        </section>

        <section className="mt-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Signal weights
          </h3>
          {numberGrid(weights, setWeights, 'weight')}
        </section>

        <section className="mt-4 space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Tier lists &amp; domain taxonomy
          </h3>
          <p className="text-[11px] text-slate-500">
            These change NORMALIZATION as well as scoring, so a recalculation re-reads every
            stored raw profile.
          </p>
          {listField('inst-tier-1', 'Institutions — tier 1', instTier1, setInstTier1)}
          {listField('inst-tier-2', 'Institutions — tier 2', instTier2, setInstTier2)}
          {listField('health-tier-1', 'Health employers — tier 1', healthTier1, setHealthTier1)}
          {listField('health-industries', 'Health industries', healthIndustries,
                     setHealthIndustries)}
        </section>

        <div className="sticky bottom-0 mt-5 flex gap-2 border-t border-slate-200 bg-white py-3">
          <button type="button" onClick={() => void save()} disabled={saving}
                  className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white
                             disabled:opacity-50">
            {saving ? 'Saving…' : 'Save configuration'}
          </button>
          <button type="button" onClick={onClose}
                  className="rounded border border-slate-300 px-3 py-1.5 text-sm">
            Cancel
          </button>
          <p className="ml-auto self-center text-[11px] text-slate-500">
            Saving never rescores.
          </p>
        </div>
      </aside>
    </div>
  )
}
