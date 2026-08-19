// Shapes mirrored from the FastAPI read models. The frontend never recomputes a
// machine dimension — it renders what the API decided.

export type Attention = 'PRIORITY_REVIEW' | 'REVIEW' | 'ROUTINE'
export type Potential = 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN'
export type DataState = 'SUFFICIENT' | 'PARTIAL' | 'NEEDS_INFORMATION'
export type RecommendedAction =
  | 'CONSIDER_ENGAGEMENT' | 'HUMAN_REVIEW' | 'RESEARCH' | 'NO_URGENT_ACTION'
export type Stage =
  | 'NEW' | 'ASSESSMENT' | 'POTENTIAL' | 'NURTURING' | 'KEEP_WARM' | 'DEAL' | 'CLOSED'
export type Disposition = 'NEEDS_REVIEW' | 'POTENTIAL' | 'NOT_NOW' | 'NEEDS_INFORMATION'

export interface QueueRow {
  founder_id: string
  mdm_person_id: string | null
  attention: Attention
  potential: Potential
  confidence: number
  data_state: DataState
  recommended_action: RecommendedAction
  broad_score: number
  archetype: string | null
  exceptional: boolean
  exceptional_count: number
  why_surfaced: string[]
  assessment_version: number
  assessed_at: string
  rubric_version: string
  duplicate_count: number
  stage: Stage | null
  owner: string | null
  next_action: string | null
  keep_warm_until: string | null
  due: boolean
  /** Human / time-derived obligations. Kept apart from `why_surfaced`, which is
   *  the machine's reasoning — a due keep-warm date is a commitment coming
   *  round, not the model changing its mind. */
  workflow_reasons: string[]
  keep_warm_inconsistent: boolean
  current_decision: Disposition | null
  decided_at: string | null
  notes_count: number
  stage_changed_at: string | null
  created_at: string
}

export interface QueueResponse {
  total: number
  as_of: string
  limit: number
  offset: number
  rows: QueueRow[]
}

export interface Signal {
  name: string
  value: number
  strength: 'STRONG' | 'MEDIUM' | 'WEAK' | 'NONE'
  source_fields: string[]
  type: 'OBSERVED' | 'DERIVED' | 'AI_INTERPRETED'
  explanation: string
  observed: boolean
}

export interface PolicyTraceItem {
  rule: string
  fired: boolean
  condition: string
  evidence: string
  sets: Record<string, string>
  overrode: Record<string, string>
  preserved: Record<string, string>
  note: string
}

export interface Assessment {
  person_id: string
  broad_score: number
  signals: Signal[]
  exceptional: {
    flag: boolean
    rule: string
    signals: Signal[]
    not_fired: Record<string, string>
  }
  confidence: number
  confidence_breakdown: {
    confidence: number
    coverage: number
    coverage_components: Record<string, number>
    coverage_subcomponents: Record<string, Record<string, number>>
    contradictions: string[]
    inferences: string[]
    [k: string]: unknown
  }
  archetype: {
    archetype: string
    strong_signals: string[]
    missing_for_archetype: string[]
    secondary: string[]
    explanation: string
  }
  potential: Potential
  attention: Attention
  data_state: DataState
  recommended_action: RecommendedAction
  missing: { code: string; detail: string; source_fields: string[] }[]
  contradictions: { code: string; detail: string; source_fields: string[]; value: unknown }[]
  policy_trace: PolicyTraceItem[]
  fired_rules: string[]
  assessment_version: string
  rubric_version: string
}

export interface CanonicalRole {
  index: number
  raw_index: number
  title: string | null
  company: string | null
  industry: string | null
  start_date: { year: number; month: number; inferred_month: boolean } | null
  end_date: { year: number; month: number; inferred_month: boolean } | null
  is_current: 'YES' | 'NO' | 'UNKNOWN'
  duration_months: number | null
  management_level: string | null
  company_size: number | null
  health_flag?: 'YES' | 'NO' | 'UNKNOWN'
  founder_title_flag?: 'EXPLICIT' | 'POSSIBLE' | 'NONE'
  flags?: { code: string; kind: string; detail: string; source_fields: string[] }[]
  [k: string]: unknown
}

export interface FounderDetail {
  founder_id: string
  facts: {
    mdm_person_id: string | null
    funnel: string | null
    source: string | null
    created_at: string
    raw: Record<string, unknown>
    canonical: {
      person_id: string
      headline: string | null
      roles: CanonicalRole[]
      education: Record<string, unknown>[]
      totals: Record<string, unknown>
      duplicates: Record<string, unknown>[]
      flags: { code: string; kind: string; detail: string; source_fields: string[] }[]
      [k: string]: unknown
    }
  }
  assessment: Assessment
  assessment_metadata: {
    assessment_version: number
    assessed_at: string
    rubric_version: string
    engine_version: string
  }
  current_decision: { disposition: Disposition; reason: string; actor: string; at: string } | null
  decision_history: { disposition: Disposition; reason: string; actor: string; at: string }[]
  workflow: {
    stage: Stage
    owner: string | null
    next_action: string | null
    keep_warm_until: string | null
    notes: { text: string; actor: string; at: string }[]
    stage_changed_at: string
    due: boolean
    workflow_reasons: string[]
    keep_warm_inconsistent: boolean
    allowed_transitions: Stage[]
  } | null
  duplicates: { links: Record<string, unknown>[]; auto_merged: boolean; policy: string }
}

export interface AuditEvent {
  id: number
  actor: string
  event: 'DECISION' | 'STAGE' | 'NOTE' | 'WORKFLOW' | 'RESCORE'
  field: string
  from: string | null
  to: string | null
  reason: string | null
  at: string
}

export interface Dashboard {
  as_of: string
  founders: number
  stage_counts: Record<Stage, number>
  weekly_intake: { week_starting: string; count: number }[]
  ageing_in_stage: Record<string, number>
  median_days_in_stage: number
  stuck: { threshold_days: number; count: number; comparison: string;
           excluded_stages: string[] }
  re_engagement_due: number
  keep_warm_inconsistent: number
  review_queue_size: number
  attention_distribution: Partial<Record<Attention, number>>
  potential_distribution: Partial<Record<Potential, number>>
  data_state_distribution: Partial<Record<DataState, number>>
  low_confidence_pct: number
  low_confidence_threshold: number
  human_decisions_recorded: number
}

export interface AILayerStatus {
  provider: string
  available: boolean
  detail: string
  prompt_version: string
  prompt_sha256: string
}

export interface AICheckResponse {
  founder_id: string
  deterministic_assessment: Assessment
  ai_evidence: {
    category: string
    strength: string
    claim: string
    source_fields: string[]
    signal: Signal
    metadata: {
      provider: string; model: string; prompt_version: string
      prompt_sha256: string; generated_at: string
      settings: Record<string, unknown>; usage: Record<string, unknown>
      latency_ms: number | null
    }
  }[]
  discarded_evidence: { claim: string; source_fields: string[]; reason: string;
                        detail: string }[]
  unsupported_inferences: string[]
  attention_before: Attention
  attention_with_ai: Attention
  attention_changed: boolean
  attention_change_reason: string
  aggregate_override: boolean
  aggregate_rule: string
  available: boolean
  provider: string
  status: 'ok' | 'unavailable' | 'error' | 'malformed'
  detail: string
}

export interface EffectiveConfig {
  rubric_version: string
  updated_at: string
  updated_by: string | null
  ai_layer?: AILayerStatus
  config: {
    weights: {
      thresholds: Record<string, number>
      signal_weights: Record<string, number>
      [k: string]: unknown
    }
    institutions: { tier_1: string[]; tier_2: string[]; [k: string]: unknown }
    health: { tier_1: string[]; tier_2: string[]; health_industries: string[];
              [k: string]: unknown }
    archetypes: Record<string, unknown>
  }
}
