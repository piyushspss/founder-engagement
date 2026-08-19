/**
 * CP9 — resurfacing in the interface.
 *
 * The claim being defended: a keep-warm date falling due is a HUMAN commitment
 * coming round, not the machine changing its mind. The UI must show it as such,
 * must never fold it into the machine's reasoning, and must still require a
 * person to press a button with a reason before anything moves.
 */

import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { WorkflowReasonBadge } from '../../components/Badges'
import { assessment, effectiveConfig, founder } from '../../test/fixtures'
import ActionPanel from './ActionPanel'
import ConfigDrawer from './ConfigDrawer'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const keepWarm = (over: { due?: boolean; until?: string | null } = {}) => founder({
  assessment: assessment({ attention: 'ROUTINE', potential: 'LOW', data_state: 'SUFFICIENT',
                           recommended_action: 'NO_URGENT_ACTION' }),
  current_decision: { disposition: 'POTENTIAL', reason: 'worth a second look',
                      actor: 'piyush', at: '2026-08-19T10:00:00' },
  workflow: {
    stage: 'KEEP_WARM',
    owner: 'dana',
    next_action: 'check in after Series A',
    keep_warm_until: over.until === undefined ? '2027-02-19' : over.until,
    notes: [{ text: 'met at HLTH', actor: 'piyush', at: '2026-08-19T10:00:00' }],
    stage_changed_at: '2026-08-19T10:00:00',
    due: over.due ?? true,
    workflow_reasons: over.due === false ? [] : ['Re-engagement due'],
    keep_warm_inconsistent: false,
    allowed_transitions: ['NURTURING', 'DEAL', 'CLOSED'],
  },
})

// ------------------------------------------- workflow reason vs machine reason
describe('a workflow obligation is not a machine signal', () => {
  it('renders the due badge distinctly from any attention pill', () => {
    render(<WorkflowReasonBadge reason="Re-engagement due" />)
    const badge = screen.getByTestId('workflow-due')
    expect(badge).toHaveTextContent('Re-engagement due')
    // not styled as an attention pill, and explicitly says the assessment is unchanged
    expect(badge.className).not.toMatch(/rounded-full/)
    expect(badge.getAttribute('title')).toMatch(/machine assessment has not changed/i)
  })

  it('coexists with a ROUTINE machine assessment without contradiction', () => {
    const detail = keepWarm()
    render(<ActionPanel detail={detail} actor="piyush" onDone={() => {}} />)
    expect(screen.getByTestId('workflow-due')).toBeVisible()
    // The panel is the HUMAN side: it states no machine dimension. ("Potential"
    // does appear — as a human DISPOSITION option, which is a different word for
    // a different thing, and is exactly the boundary CP7 froze.)
    const text = screen.getByTestId('human-decision-panel').textContent ?? ''
    expect(text).not.toMatch(/routine|priority review|attention|confidence|data state/i)
    expect(text).toMatch(/Re-engagement due/)
  })

  it('flags an inconsistent keep-warm record instead of guessing a date', () => {
    render(<WorkflowReasonBadge reason="Keep-warm date missing — inconsistent workflow data" />)
    const badge = screen.getByTestId('workflow-inconsistent')
    expect(badge.getAttribute('title')).toMatch(/will not guess a date/i)
    expect(badge.getAttribute('title')).toMatch(/will not.*surface them as due/i)
  })
})

// --------------------------------------------------------------- re-engage
describe('the Re-engage action', () => {
  it('appears only for founders in KEEP_WARM', () => {
    const { unmount } = render(
      <ActionPanel detail={keepWarm()} actor="piyush" onDone={() => {}} />)
    expect(screen.getByTestId('reengage-button')).toHaveTextContent('Re-engage')
    unmount()

    render(<ActionPanel detail={founder()} actor="piyush" onDone={() => {}} />)
    expect(screen.queryByTestId('reengage-button')).toBeNull()
  })

  it('labels an early re-engagement honestly and does not claim the founder is due', () => {
    render(<ActionPanel detail={keepWarm({ due: false })} actor="piyush" onDone={() => {}} />)
    expect(screen.getByTestId('reengage-button')).toHaveTextContent('Re-engage early')
    expect(screen.queryByTestId('workflow-due')).toBeNull()
    expect(document.body.textContent).toMatch(/not counted as due/i)
  })

  it('still requires a human reason — it only pre-selects the target stage', async () => {
    const user = userEvent.setup()
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    render(<ActionPanel detail={keepWarm()} actor="piyush" onDone={() => {}} />)

    await user.click(screen.getByTestId('reengage-button'))
    expect((screen.getByLabelText('Move to') as HTMLSelectElement).value).toBe('NURTURING')
    expect(fetchSpy).not.toHaveBeenCalled()          // pressing it writes nothing

    await user.click(screen.getByRole('button', { name: /move stage/i }))
    expect(fetchSpy).not.toHaveBeenCalled()          // the reason field is required
  })

  it('posts NURTURING through the ordinary stage endpoint with a reason', async () => {
    const user = userEvent.setup()
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify({ founder_id: 'f-1', from: 'KEEP_WARM', to: 'NURTURING',
                       keep_warm_until: null }),
      { status: 200, headers: { 'content-type': 'application/json' } }))
    render(<ActionPanel detail={keepWarm()} actor="piyush" onDone={() => {}} />)

    await user.click(screen.getByTestId('reengage-button'))
    await user.type(screen.getByLabelText(/Reason \(required\)/i, { selector: '#stage-reason' }),
      'keep-warm date reached, re-engaging')
    await user.click(screen.getByRole('button', { name: /move stage/i }))

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1))
    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toContain('/founders/f-1/stage')
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({
      stage: 'NURTURING', actor: 'piyush', reason: 'keep-warm date reached, re-engaging',
    })
    // one call only: re-engaging does not also write a disposition
    expect(fetchSpy.mock.calls.filter(([u]) => String(u).includes('/decision'))).toHaveLength(0)
  })

  it('does not offer disallowed backward stages', async () => {
    render(<ActionPanel detail={keepWarm()} actor="piyush" onDone={() => {}} />)
    const options = within(screen.getByLabelText('Move to') as HTMLSelectElement)
      .getAllByRole('option').map((o) => (o as HTMLOptionElement).value)
    expect(options).toEqual(['', 'NURTURING', 'DEAL', 'CLOSED'])
    expect(options).not.toContain('ASSESSMENT')
    expect(options).not.toContain('NEW')
  })
})

// ----------------------------------------------------------------- F-18 copy
describe('F-18 — recalculation copy does not overstate', () => {
  it('says assessments were re-evaluated, not that conclusions changed', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, init) => {
      const method = (init as RequestInit)?.method
      if (method === 'PUT') {
        return new Response(JSON.stringify({ rubric_version_before: 'a'.repeat(64),
                                             rubric_version: 'b'.repeat(64), rescored: false,
                                             note: '' }),
                            { status: 200, headers: { 'content-type': 'application/json' } })
      }
      return new Response(JSON.stringify({ founders_rescored: 800, assessments_changed: 800,
                                           canonical_profiles_changed: 0,
                                           human_state_touched: false,
                                           rubric_version: 'b'.repeat(64) }),
                          { status: 200, headers: { 'content-type': 'application/json' } })
    })

    render(<ConfigDrawer open onClose={() => {}} config={effectiveConfig()} actor="piyush"
                        onSaved={() => {}} onRescored={() => {}} />)
    await user.click(screen.getByRole('button', { name: /save configuration/i }))
    await user.click(await screen.findByRole('button', { name: /recalculate assessments/i }))

    const result = await screen.findByText(/re-evaluated and rewritten/i)
    expect(result).toBeVisible()
    expect(result.textContent).toMatch(/not founders whose conclusion changed/i)
    expect(result.textContent).not.toMatch(/800 assessments changed/)
  })
})
