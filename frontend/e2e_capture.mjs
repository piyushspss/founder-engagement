/**
 * CP8 evidence capture. Drives the REAL UI against the REAL API and records
 * every screenshot and every console message. No mocking anywhere.
 */
import { chromium } from 'playwright'
import fs from 'node:fs'

const OUT = '/Users/piyushchandra/founder-engagement/docs/cp8'
const BASE = 'http://localhost:5173'
const API = 'http://127.0.0.1:8000'

const IDS = {
  demo: '021ceb3f-a1ba-4508-89e1-5f8e2feed1da',      // PRIORITY_REVIEW, exceptional
  unknown: '6ddfa6e8-7556-432c-84cb-9bc9a77fec16',   // PRIORITY_REVIEW + UNKNOWN
  low: '0487b053-7700-4fd2-943d-814db52e1303',       // LOW
  partial: '15db3b29-f100-4e3b-9cdb-79add72af8e2',   // PARTIAL
  contradiction: 'e3decc3b-ab5e-452a-9902-f0cc417b9c40', // OVERLAP + missing + PARTIAL
  cue: '0b271a3a-b117-4441-ae7b-c8507a3f37b3',       // MEDIUM cue, aggregate false
}

const console_log = []
const transcript = []

const shot = async (page, name, opts = {}) => {
  await page.waitForTimeout(350)
  await page.screenshot({ path: `${OUT}/${name}.png`, ...opts })
  transcript.push(`SHOT ${name}`)
  console.log('shot', name)
}

const run = async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  page.on('console', (m) => console_log.push(`[${m.type()}] ${m.text()}`))
  page.on('pageerror', (e) => console_log.push(`[pageerror] ${e.message}`))
  page.on('requestfailed', (r) =>
    console_log.push(`[requestfailed] ${r.method()} ${r.url()} ${r.failure()?.errorText}`))
  page.on('response', (r) => {
    if (r.url().includes('/api/') && r.status() >= 400) {
      console_log.push(`[api ${r.status()}] ${r.request().method()} ${r.url()}`)
    }
    if (r.url().includes('/api/') && ['POST', 'PUT', 'PATCH'].includes(r.request().method())) {
      transcript.push(`${r.request().method()} ${r.url().replace('/api', '')} -> ${r.status()}`)
    }
  })

  // ---------------------------------------------------------- 1. queue
  await page.goto(`${BASE}/#/`, { waitUntil: 'networkidle' })
  await page.waitForSelector('table')
  await shot(page, '01-priority-queue-default')

  // ---------------------------------------------------------- 2. filters
  await page.getByText('priority review', { exact: true }).click()
  await page.getByText('needs information', { exact: true }).click()
  await page.waitForTimeout(600)
  await shot(page, '02-priority-queue-filtered')
  await page.getByRole('button', { name: 'Clear all' }).click()
  await page.waitForTimeout(400)

  // ------------------------------------------- 3/4/5 founder detail
  await page.goto(`${BASE}/#/founders/${IDS.demo}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('#assessment-heading')
  await shot(page, '03-founder-detail-assessment')

  await page.locator('summary', { hasText: 'sources & explanation' }).first().click()
  await page.locator('summary', { hasText: 'not observed — why' }).first().click()
  await page.locator('#why-heading').scrollIntoViewIfNeeded()
  await shot(page, '04-founder-detail-evidence-provenance')

  await page.locator('#human-heading').scrollIntoViewIfNeeded()
  await shot(page, '05-founder-detail-human-decision-panel')

  // -------------------------------------------------- end-to-end flow
  transcript.push('--- END-TO-END HUMAN FLOW (all actions performed through the UI) ---')
  await page.getByLabel('Disposition').selectOption('POTENTIAL')
  await page.locator('#disposition-reason').fill(
    'MD + health-system leadership + exceptional evidence threshold met')
  await page.getByRole('button', { name: 'Record disposition' }).click()
  await page.waitForTimeout(700)

  for (const [stage, reason] of [
    ['ASSESSMENT', 'picked up from the priority queue'],
    ['POTENTIAL', 'evidence holds up on read'],
    ['NURTURING', 'warm intro through the Mayo network'],
  ]) {
    await page.locator('#stage-target').selectOption(stage)
    await page.locator('#stage-reason').fill(reason)
    await page.getByRole('button', { name: 'Move stage' }).click()
    await page.waitForTimeout(700)
  }

  await page.locator('#stage-target').selectOption('KEEP_WARM')
  await page.waitForTimeout(200)
  await page.locator('#keep-warm-months').selectOption('6')
  await page.locator('#stage-reason').fill('too early — revisit after their next raise')
  await page.getByRole('button', { name: 'Move stage' }).click()
  await page.waitForTimeout(800)

  await page.locator('#owner-input').fill('dana')
  await page.locator('#next-action-input').fill('check in after Series A')
  await page.locator('#workflow-reason').fill('assigning ownership for the warm period')
  await page.getByRole('button', { name: 'Update owner / next action' }).click()
  await page.waitForTimeout(700)

  await page.locator('#note-input').fill(
    'Met at HLTH. Wants a co-founder, not capital, right now.')
  await page.getByRole('button', { name: 'Append note' }).click()
  await page.waitForTimeout(800)

  await page.locator('#human-heading').scrollIntoViewIfNeeded()
  await shot(page, '12-end-to-end-final-keep-warm')

  await page.locator('#audit-heading').scrollIntoViewIfNeeded()
  await page.waitForTimeout(300)
  await shot(page, '06-founder-detail-audit-history')

  // -------------------------------------- 10a/10b UNKNOWN vs LOW
  await page.goto(`${BASE}/#/founders/${IDS.unknown}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('#assessment-heading')
  await shot(page, '10a-unknown-presentation',
    { clip: { x: 0, y: 90, width: 1440, height: 430 } })

  await page.goto(`${BASE}/#/founders/${IDS.low}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('#assessment-heading')
  await shot(page, '10b-low-presentation',
    { clip: { x: 0, y: 90, width: 1440, height: 430 } })

  // ------------------------------- 11 MEDIUM cue, aggregate false
  await page.goto(`${BASE}/#/founders/${IDS.cue}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('#exceptional-heading')
  await page.locator('#exceptional-heading').scrollIntoViewIfNeeded()
  await shot(page, '11-medium-cue-aggregate-false')

  // ------------------------------- 13 contradictions / missing / PARTIAL
  await page.goto(`${BASE}/#/founders/${IDS.contradiction}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('#uncertainty-heading')
  await page.locator('#uncertainty-heading').scrollIntoViewIfNeeded()
  await shot(page, '13-contradictions-and-missing')
  await page.locator('#timeline-heading').scrollIntoViewIfNeeded()
  await shot(page, '14-normalized-timeline')

  await page.goto(`${BASE}/#/founders/${IDS.partial}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('#assessment-heading')
  await shot(page, '15-partial-data-state',
    { clip: { x: 0, y: 90, width: 1440, height: 430 } })

  // ------------------------------------------------- 7/8 pipeline
  await page.goto(`${BASE}/#/pipeline`, { waitUntil: 'networkidle' })
  await page.waitForSelector('#pipeline-heading')
  await shot(page, '07-pipeline-kanban')
  await page.locator('#dashboard-heading').scrollIntoViewIfNeeded()
  await page.waitForTimeout(400)
  await shot(page, '08-dashboard')

  // --------------------------- 16 invalid transition through the board
  await page.getByRole('link', { name: /021ceb3f/ }).first().waitFor()
  const card = page.locator('div', { has: page.getByRole('link', { name: /021ceb3f/ }) }).last()
  await card.getByRole('button', { name: 'Move stage…' }).click()
  await page.waitForTimeout(600)
  await card.getByLabel('Show every stage (the API will refuse disallowed moves)').check()
  await card.getByLabel('Target stage').selectOption('ASSESSMENT')
  await card.getByPlaceholder('Reason').fill('attempting a backward move on purpose')
  await card.getByRole('button', { name: 'Move', exact: true }).click()
  await page.waitForTimeout(800)
  await card.scrollIntoViewIfNeeded()
  await shot(page, '16-invalid-transition-409')
  await card.getByRole('button', { name: 'Cancel' }).click()

  // --------------------------------------------- 9 config drawer
  await page.getByRole('button', { name: 'Configuration' }).click()
  await page.waitForSelector('#config-heading')
  await shot(page, '09-config-drawer')

  await browser.close()
  fs.writeFileSync(`${OUT}/console.log`, console_log.join('\n') || '(no console output)')
  fs.writeFileSync(`${OUT}/ui-transcript.log`, transcript.join('\n'))
  console.log('\n--- console messages:', console_log.length)
  console_log.forEach((l) => console.log('   ', l))
}

run().catch((e) => { console.error(e); process.exit(1) })
