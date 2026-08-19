/**
 * The tests that protect the product's meaning, not its markup.
 *
 * Each one corresponds to a documented finding or a frozen boundary:
 * F-9 (UNKNOWN is not a bad LOW), F-13 (a cue is not the aggregate state), the
 * machine/human boundary, and "config save never rescores".
 */

import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PotentialChip } from '../../components/Badges'
import { POTENTIAL, POTENTIAL_SENTENCE } from '../../vocab'
import { assessment, auditEvents, effectiveConfig, founder, signal } from '../../test/fixtures'
import ActionPanel from './ActionPanel'
import AssessmentCard from './AssessmentCard'
import AuditPanel from './AuditPanel'
import ConfigDrawer from './ConfigDrawer'
import ExceptionalPanel from './ExceptionalPanel'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()   // fetch spies must not leak call history between tests
})

// --------------------------------------------------------------- F-9
describe('F-9 — UNKNOWN is an unmade judgment, not a worse LOW', () => {
  it('does not reuse LOW styling or copy for UNKNOWN', () => {
    expect(POTENTIAL.UNKNOWN.className).not.toBe(POTENTIAL.LOW.className)
    expect(POTENTIAL.UNKNOWN.label).not.toMatch(/low/i)
    expect(POTENTIAL.UNKNOWN.help).toMatch(/insufficient evidence/i)
    expect(POTENTIAL_SENTENCE.LOW).toMatch(/sufficient evidence/i)
  })

  it('never renders UNKNOWN in a negative colour or with judgemental words', () => {
    render(<PotentialChip value="UNKNOWN" withHint />)
    const chip = screen.getByTestId('potential-UNKNOWN')
    expect(chip.className).not.toMatch(/red|rose|danger/)
    expect(chip.textContent).toBe('Unknown')
    expect(document.body.textContent).not.toMatch(/poor|bad|weak candidate|reject/i)
    expect(document.body.textContent).toMatch(/insufficient evidence to judge/i)
  })

  it('reads coherently as PRIORITY_REVIEW + UNKNOWN', () => {
    render(<AssessmentCard detail={founder()} effectiveRubric={'a'.repeat(64)} />)
    expect(screen.getByTestId('attention-PRIORITY_REVIEW')).toHaveTextContent('Priority Review')
    expect(screen.getByTestId('potential-UNKNOWN')).toHaveTextContent('Unknown')
    // the two dimensions are rendered as separate elements, never one badge
    expect(screen.getByTestId('attention-PRIORITY_REVIEW'))
      .not.toContainElement(screen.getByTestId('potential-UNKNOWN'))
  })
})

// -------------------------------------------------------------- F-13
describe('F-13 — a detector cue is not the aggregated exceptional state', () => {
  it('shows a MEDIUM cue while stating the override did not trigger', () => {
    const a = assessment({
      exceptional: {
        flag: false,
        rule: '1 MEDIUM detector (< 2 required)',
        signals: [signal({ name: 'exceptional_progression', strength: 'MEDIUM',
                           explanation: 'Four levels in three years.' })],
        not_fired: { repeat_founder: 'only one explicit founder role' },
      },
    })
    render(<ExceptionalPanel assessment={a} />)

    expect(screen.getByTestId('exceptional-aggregate')).toHaveTextContent('No')
    expect(screen.getByTestId('cue-exceptional_progression')).toHaveTextContent('Medium')
    expect(screen.getByTestId('cue-exceptional_progression'))
      .toHaveTextContent(/unusual evidence cue/i)
    expect(document.body.textContent).not.toMatch(/this founder is exceptional/i)
    expect(document.body.textContent).toMatch(/priority override triggered/i)
  })

  it('states the override plainly when the aggregate DID fire', () => {
    const a = assessment({
      exceptional: { flag: true, rule: '2 MEDIUM detectors (>= 2)',
                     signals: [signal({ name: 'exceptional_credential', strength: 'MEDIUM' }),
                               signal({ name: 'exceptional_progression', strength: 'MEDIUM' })],
                     not_fired: {} },
    })
    render(<ExceptionalPanel assessment={a} />)
    expect(screen.getByTestId('exceptional-aggregate')).toHaveTextContent('Yes')
  })
})

// ------------------------------------------- machine / human boundary
describe('machine / human boundary', () => {
  it('keeps the Human decision panel separate from the assessment', () => {
    const detail = founder()
    render(
      <>
        <AssessmentCard detail={detail} effectiveRubric={'a'.repeat(64)} />
        <ActionPanel detail={detail} actor="piyush" onDone={() => {}} />
      </>,
    )
    const assessmentSection = screen.getByRole('region', { name: /machine assessment/i })
    const humanPanel = screen.getByTestId('human-decision-panel')
    expect(humanPanel).not.toContainElement(assessmentSection)
    expect(assessmentSection).not.toContainElement(humanPanel)
    // no disposition or stage control lives inside the assessment section
    expect(within(assessmentSection).queryByRole('button')).toBeNull()
    expect(within(assessmentSection).queryByRole('combobox')).toBeNull()
    expect(within(humanPanel).getByRole('heading', { name: 'Human decision' })).toBeVisible()
  })

  it('never turns recommended_action into an automatic mutation', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    const detail = founder({
      assessment: assessment({ recommended_action: 'CONSIDER_ENGAGEMENT' }),
    })
    render(<ActionPanel detail={detail} actor="piyush" onDone={() => {}} />)

    // rendering the panel for a CONSIDER_ENGAGEMENT founder writes nothing
    expect(fetchSpy).not.toHaveBeenCalled()
    // and there is no one-click "accept the recommendation" shortcut
    expect(screen.queryByRole('button', { name: /accept|apply recommendation|engage/i }))
      .toBeNull()
    // the disposition defaults to the neutral option, not to the recommendation
    expect((screen.getByLabelText('Disposition') as HTMLSelectElement).value)
      .toBe('NEEDS_REVIEW')
  })

  it('sends disposition and stage as two separate API calls', async () => {
    const user = userEvent.setup()
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }))
    render(<ActionPanel detail={founder()} actor="piyush" onDone={() => {}} />)

    await user.selectOptions(screen.getByLabelText('Disposition'), 'POTENTIAL')
    await user.type(
      screen.getByLabelText(/Reason \(required\)/i, { selector: '#disposition-reason' }),
      'strong evidence')
    await user.click(screen.getByRole('button', { name: /record disposition/i }))

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1))
    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toContain('/decision')
    expect(JSON.parse(String((init as RequestInit).body))).toMatchObject({
      disposition: 'POTENTIAL', actor: 'piyush', reason: 'strong evidence',
    })
    // the disposition call did NOT also move a stage
    expect(String(url)).not.toContain('/stage')
  })

  it('surfaces an invalid transition without changing anything on screen', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify({ error: 'invalid_transition',
                       detail: 'NEW -> DEAL is not an allowed transition; allowed from NEW: '
                             + 'ASSESSMENT, CLOSED' }),
      { status: 409, headers: { 'content-type': 'application/json' } }))
    const onDone = vi.fn()
    render(<ActionPanel detail={founder()} actor="piyush" onDone={onDone} />)

    await user.selectOptions(screen.getByLabelText('Move to'), 'ASSESSMENT')
    await user.type(screen.getByLabelText(/Reason \(required\)/i, { selector: '#stage-reason' }),
      'triage')
    await user.click(screen.getByRole('button', { name: /move stage/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/not an allowed transition/i)
    expect(alert).toHaveTextContent(/allowed from NEW/i)
    expect(onDone).not.toHaveBeenCalled()          // nothing was refreshed = nothing changed
  })
})

// ------------------------------------------------------------- audit
describe('audit history', () => {
  it('distinguishes a system RESCORE from a human action', () => {
    render(<AuditPanel events={auditEvents()} />)
    const system = screen.getByTestId('audit-system')
    const human = screen.getByTestId('audit-human')
    expect(system).toHaveTextContent(/system/i)
    expect(system).toHaveTextContent(/assessment recalculated/i)
    expect(system).toHaveTextContent(/workflow untouched/i)
    expect(system.textContent).not.toMatch(/stage/i)
    expect(human).toHaveTextContent(/human/i)
    expect(human).toHaveTextContent(/Stage: stage/i)
    expect(human).toHaveTextContent(/NURTURING/)
  })
})

// --------------------------------------------------- config + freshness
describe('config drawer and assessment freshness', () => {
  it('saving configuration does not rescore', async () => {
    const user = userEvent.setup()
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify({ rubric_version_before: 'a'.repeat(64), rubric_version: 'b'.repeat(64),
                       rescored: false, note: 'no founder was rescored' }),
      { status: 200, headers: { 'content-type': 'application/json' } }))

    render(<ConfigDrawer open onClose={() => {}} config={effectiveConfig()} actor="piyush"
                        onSaved={() => {}} onRescored={() => {}} />)
    await user.clear(screen.getByLabelText('priority broad'))
    await user.type(screen.getByLabelText('priority broad'), '55')
    await user.click(screen.getByRole('button', { name: /save configuration/i }))

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    const calls = fetchSpy.mock.calls.map(([url, init]) =>
      `${(init as RequestInit)?.method ?? 'GET'} ${String(url)}`)
    expect(calls).toEqual(['PUT /api/config'])
    expect(calls.join()).not.toContain('/rescore')
    expect(await screen.findByText(/older rubric/i)).toBeVisible()
  })

  it('says list fields are replaced wholesale', () => {
    render(<ConfigDrawer open onClose={() => {}} config={effectiveConfig()} actor="piyush"
                        onSaved={() => {}} onRescored={() => {}} />)
    expect(screen.getByText(/List fields are replaced, not merged/i)).toBeVisible()
    expect(screen.getAllByText(/saving replaces the whole list/i).length).toBeGreaterThan(0)
    expect(document.body.textContent)
      .toMatch(/does not automatically change human decisions or workflow/i)
  })

  it('sends the complete list, not a patch', async () => {
    const user = userEvent.setup()
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify({ rubric_version_before: 'a', rubric_version: 'b', rescored: false,
                       note: '' }),
      { status: 200, headers: { 'content-type': 'application/json' } }))
    render(<ConfigDrawer open onClose={() => {}} config={effectiveConfig()} actor="piyush"
                        onSaved={() => {}} onRescored={() => {}} />)

    const box = screen.getByLabelText(/Institutions — tier 1/i)
    await user.clear(box)
    await user.type(box, 'Harvard University\nJohns Hopkins University')
    await user.click(screen.getByRole('button', { name: /save configuration/i }))

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    const put = fetchSpy.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT')!
    const body = JSON.parse(String((put[1] as RequestInit).body))
    expect(body.config.institutions.tier_1)
      .toEqual(['Harvard University', 'Johns Hopkins University'])
  })

  it('flags a stale rubric on the founder detail, and stays quiet when fresh', () => {
    const detail = founder()
    const { unmount } = render(
      <AssessmentCard detail={detail} effectiveRubric={'b'.repeat(64)} />)
    expect(screen.getByText(/Assessment needs recalculation/i)).toBeVisible()
    unmount()

    render(<AssessmentCard detail={detail} effectiveRubric={'a'.repeat(64)} />)
    expect(screen.queryByText(/Assessment needs recalculation/i)).toBeNull()
  })
})
