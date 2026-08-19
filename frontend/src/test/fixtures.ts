import type { Assessment, AuditEvent, EffectiveConfig, FounderDetail, Signal } from '../types'

export function signal(over: Partial<Signal> = {}): Signal {
  return {
    name: 'leadership', value: 0.8, strength: 'STRONG', source_fields: ['experience[0].title'],
    type: 'DERIVED', explanation: 'Highest management level held: VP.', observed: true, ...over,
  }
}

export function assessment(over: Partial<Assessment> = {}): Assessment {
  return {
    person_id: 'f-1',
    broad_score: 71.2,
    signals: [signal(), signal({ name: 'founder_evidence', value: 0, strength: 'NONE',
                                 observed: false, source_fields: [],
                                 explanation: 'No explicit founder title observed.' })],
    exceptional: { flag: false, rule: '1 MEDIUM detector (< 2 required)', signals: [],
                   not_fired: {} },
    confidence: 0.72,
    confidence_breakdown: { confidence: 0.72, coverage: 0.8, coverage_components: {},
                            coverage_subcomponents: {}, contradictions: [], inferences: [] },
    archetype: { archetype: 'Healthcare Operator', strong_signals: ['leadership'],
                 missing_for_archetype: [], secondary: [], explanation: '' },
    potential: 'UNKNOWN',
    attention: 'PRIORITY_REVIEW',
    data_state: 'PARTIAL',
    recommended_action: 'CONSIDER_ENGAGEMENT',
    missing: [], contradictions: [], policy_trace: [], fired_rules: [],
    assessment_version: 'cp5.1',
    rubric_version: 'a'.repeat(64),
    ...over,
  }
}

export function founder(over: Partial<FounderDetail> = {}): FounderDetail {
  return {
    founder_id: 'f-1',
    facts: {
      mdm_person_id: 'f-1', funnel: 'TEST', source: 'test',
      created_at: '2026-08-01T00:00:00',
      raw: {},
      canonical: { person_id: 'f-1', headline: 'VP Clinical Operations', roles: [],
                   education: [], totals: {}, duplicates: [], flags: [] },
    },
    assessment: assessment(),
    assessment_metadata: { assessment_version: 1, assessed_at: '2026-08-19T10:00:00',
                           rubric_version: 'a'.repeat(64), engine_version: 'cp5.1' },
    current_decision: null,
    decision_history: [],
    workflow: { stage: 'NEW', owner: null, next_action: null, keep_warm_until: null,
                notes: [], stage_changed_at: '2026-08-19T10:00:00', due: false,
                workflow_reasons: [], keep_warm_inconsistent: false,
                allowed_transitions: ['ASSESSMENT', 'CLOSED'] },
    duplicates: { links: [], auto_merged: false, policy: 'A6b — flagged, never merged.' },
    ...over,
  }
}

export function auditEvents(): AuditEvent[] {
  return [
    { id: 1, actor: 'piyush', event: 'STAGE', field: 'stage', from: 'NURTURING',
      to: 'KEEP_WARM', reason: 'too early', at: '2026-08-19T11:00:00' },
    { id: 2, actor: 'system', event: 'RESCORE', field: 'assessment', from: 'v1 rubric aaaa',
      to: 'v2 rubric bbbb', reason: 'config change', at: '2026-08-19T12:00:00' },
  ]
}

export function effectiveConfig(over: Partial<EffectiveConfig> = {}): EffectiveConfig {
  return {
    rubric_version: 'a'.repeat(64),
    updated_at: '2026-08-19T09:00:00',
    updated_by: null,
    config: {
      weights: { thresholds: { priority_broad: 65, priority_confidence: 0.6 },
                 signal_weights: { leadership: 15, founder_evidence: 25 } },
      institutions: { tier_1: ['Harvard University'], tier_2: ['Cornell University'] },
      health: { tier_1: ['Mayo Clinic'], tier_2: [], health_industries: ['Hospital & Health Care'] },
      archetypes: {},
    },
    ...over,
  }
}
