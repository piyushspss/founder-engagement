/**
 * CP10 — the AI overlay in the interface.
 *
 * What is defended here: the panel never runs itself, never speaks about the
 * founder in recommendation language, never claims a mock result is a model
 * result, and never sits where the machine assessment or the human decision
 * belongs.
 */

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AIEvidencePanel from './AIEvidencePanel'
import type { AICheckResponse, AILayerStatus } from '../../types'
import { assessment } from '../../test/fixtures'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const status = (over: Partial<AILayerStatus> = {}): AILayerStatus => ({
  provider: 'mock', available: true, detail: '',
  prompt_version: 'cp10.1', prompt_sha256: 'a'.repeat(64), ...over,
})

const response = (over: Partial<AICheckResponse> = {}): AICheckResponse => ({
  founder_id: 'f-1',
  deterministic_assessment: assessment(),
  ai_evidence: [{
    category: 'unusual_progression', strength: 'STRONG',
    claim: 'Two roles show a jump in recorded management level.',
    source_fields: ['experience[0].management_level', 'experience[1].management_level'],
    signal: { name: 'ai_unusual_progression', value: 1, strength: 'STRONG',
              source_fields: ['experience[0].management_level'],
              type: 'AI_INTERPRETED', explanation: 'c', observed: true },
    metadata: { provider: 'mock', model: 'mock-deterministic-v1',
                prompt_version: 'cp10.1', prompt_sha256: 'a'.repeat(64),
                generated_at: '1970-01-01T00:00:00+00:00',
                settings: {}, usage: {}, latency_ms: 0 },
  }],
  discarded_evidence: [],
  unsupported_inferences: [],
  attention_before: 'REVIEW', attention_with_ai: 'PRIORITY_REVIEW',
  attention_changed: true,
  attention_change_reason: 'REVIEW -> PRIORITY_REVIEW: 1 STRONG AI cue(s)',
  aggregate_override: true, aggregate_rule: '1 STRONG AI cue(s)',
  available: true, provider: 'mock', status: 'ok', detail: '',
  ...over,
})

const mockFetch = (body: AICheckResponse) =>
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(body),
    { status: 200, headers: { 'content-type': 'application/json' } }))

describe('the AI overlay is optional and explicit', () => {
  it('runs nothing on render — the call needs a click', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    render(<AIEvidencePanel founderId="f-1" status={status()} />)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('posts to ai_check only when the button is pressed', async () => {
    const user = userEvent.setup()
    const fetchSpy = mockFetch(response())
    render(<AIEvidencePanel founderId="f-1" status={status()} />)

    await user.click(screen.getByTestId('ai-check-button'))
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1))
    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toBe('/api/founders/f-1/ai_check')
    expect((init as RequestInit).method).toBe('POST')
  })

  it('shows an honest unavailable state and disables the action', () => {
    render(<AIEvidencePanel founderId="f-1"
                            status={status({ available: false, provider: 'anthropic',
                                             detail: 'ANTHROPIC_API_KEY is not set' })} />)
    const button = screen.getByTestId('ai-check-button')
    expect(button).toHaveTextContent('AI evidence check unavailable')
    expect(button).toBeDisabled()
    expect(screen.getByText(/ANTHROPIC_API_KEY is not set/)).toBeVisible()
    expect(document.body.textContent).toMatch(/deterministic assessment is unaffected/i)
  })
})

describe('mock output is never passed off as a model result', () => {
  it('labels the mock adapter before and after the call', async () => {
    const user = userEvent.setup()
    mockFetch(response())
    render(<AIEvidencePanel founderId="f-1" status={status()} />)

    expect(screen.getByTestId('ai-check-button')).toHaveTextContent('Mock AI evidence check')
    expect(screen.getByTestId('ai-mock-label')).toHaveTextContent(/not a model result/i)

    await user.click(screen.getByTestId('ai-check-button'))
    expect(await screen.findByText(/mock-deterministic-v1/)).toBeVisible()
  })

  it('says "Run AI evidence check" only for a real provider', () => {
    render(<AIEvidencePanel founderId="f-1"
                            status={status({ provider: 'anthropic' })} />)
    expect(screen.getByTestId('ai-check-button')).toHaveTextContent('Run AI evidence check')
    expect(screen.queryByTestId('ai-mock-label')).toBeNull()
  })
})

describe('wording and subordination', () => {
  it('never uses recommendation or approval language', async () => {
    const user = userEvent.setup()
    mockFetch(response())
    render(<AIEvidencePanel founderId="f-1" status={status()} />)
    await user.click(screen.getByTestId('ai-check-button'))
    await screen.findByTestId('ai-attention')

    const text = document.body.textContent ?? ''
    for (const banned of [/AI recommends/i, /great founder/i, /predicts success/i,
                          /AI approved/i, /AI rejected/i, /best founder/i,
                          /AI selected/i]) {
      expect(text).not.toMatch(banned)
    }
    expect(text).toMatch(/AI-interpreted evidence — supplemental/)
    expect(text).toMatch(/may only raise attention, never lower it/i)
  })

  it('states an escalation as a raise, with both values', async () => {
    const user = userEvent.setup()
    mockFetch(response())
    render(<AIEvidencePanel founderId="f-1" status={status()} />)
    await user.click(screen.getByTestId('ai-check-button'))

    const line = await screen.findByTestId('ai-attention')
    expect(line).toHaveTextContent(/Attention raised from\s*REVIEW\s*to\s*PRIORITY_REVIEW/)
  })

  it('renders cues as AI_INTERPRETED with their provenance and metadata', async () => {
    const user = userEvent.setup()
    mockFetch(response())
    render(<AIEvidencePanel founderId="f-1" status={status()} />)
    await user.click(screen.getByTestId('ai-check-button'))

    expect(await screen.findByText(/unusual evidence cue/i)).toBeVisible()
    expect(screen.getByText('AI')).toBeVisible()                    // provenance badge
    expect(screen.getByText(/experience\[0\]\.management_level/)).toBeVisible()
    expect(screen.getByText(/prompt cp10\.1/)).toBeVisible()
  })

  it('is a separate section from the machine assessment and the human panel', () => {
    render(<AIEvidencePanel founderId="f-1" status={status()} />)
    const panel = screen.getByTestId('ai-evidence-panel')
    expect(panel.querySelector('#assessment-heading')).toBeNull()
    expect(panel.querySelector('[data-testid="human-decision-panel"]')).toBeNull()
    expect(panel.textContent).not.toMatch(/human decision/i)
  })
})

describe('failure and discard reporting', () => {
  it('reports a malformed provider response without claiming evidence', async () => {
    const user = userEvent.setup()
    mockFetch(response({
      status: 'malformed', ai_evidence: [], attention_changed: false,
      attention_with_ai: 'REVIEW',
      attention_change_reason: 'no accepted AI evidence',
      detail: 'provider output failed schema validation',
      discarded_evidence: [{ claim: '(provider output)', source_fields: [],
                             reason: 'MALFORMED_OUTPUT',
                             detail: 'failed schema validation' }],
    }))
    render(<AIEvidencePanel founderId="f-1" status={status()} />)
    await user.click(screen.getByTestId('ai-check-button'))

    expect(await screen.findByText(/failed validation/i)).toBeVisible()
    expect(document.body.textContent).toMatch(/deterministic assessment is unchanged/i)
    expect(screen.getByTestId('ai-attention')).toHaveTextContent(/unchanged/i)
  })

  it('shows discarded items and unsupported inferences as non-evidence', async () => {
    const user = userEvent.setup()
    mockFetch(response({
      ai_evidence: [], attention_changed: false, attention_with_ai: 'REVIEW',
      discarded_evidence: [{ claim: 'Exited to a strategic buyer.',
                             source_fields: ['experience[0].exit_details'],
                             reason: 'UNKNOWN_SOURCE_PATH',
                             detail: 'does not exist on this founder' }],
      unsupported_inferences: ['a CEO title implies founding'],
    }))
    render(<AIEvidencePanel founderId="f-1" status={status()} />)
    await user.click(screen.getByTestId('ai-check-button'))

    expect(await screen.findByText(/failed provenance validation/i)).toBeVisible()
    expect(screen.getByText(/diagnostic only, never evidence/i)).toBeVisible()
    expect(screen.getByText(/No supplemental evidence accepted/i)).toBeVisible()
  })
})
