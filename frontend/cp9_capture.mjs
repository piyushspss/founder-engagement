/** CP9 evidence capture — resurfacing across a simulated date, then Re-engage. */
import { chromium } from 'playwright'
import fs from 'node:fs'

const OUT = '/Users/piyushchandra/founder-engagement/docs/cp9'
const BASE = 'http://localhost:5173'
const FID = '021ceb3f-a1ba-4508-89e1-5f8e2feed1da'
const BEFORE = '2027-02-18'
const DUE = '2027-02-19'

fs.mkdirSync(OUT, { recursive: true })
const log = []
const console_log = []

const b = await chromium.launch()
const page = await b.newPage({ viewport: { width: 1440, height: 1000 } })
page.on('console', (m) => console_log.push(`[${m.type()}] ${m.text()}`))
page.on('pageerror', (e) => console_log.push(`[pageerror] ${e.message}`))
page.on('response', (r) => {
  if (r.url().includes('/api/') && ['POST', 'PUT', 'PATCH'].includes(r.request().method())) {
    log.push(`${r.request().method()} ${r.url().replace('/api', '')} -> ${r.status()}`)
  }
})
const shot = async (name, opts = {}) => {
  await page.waitForTimeout(400)
  await page.screenshot({ path: `${OUT}/${name}.png`, ...opts })
  log.push(`SHOT ${name}`)
  console.log('shot', name)
}
const setAsOf = async (value) => {
  await page.locator('#as-of').fill(value)
  await page.waitForTimeout(900)
}

// ---- 1. future keep-warm founder: not due -------------------------------
await page.goto(`${BASE}/#/`, { waitUntil: 'networkidle' })
await page.waitForSelector('table')
await page.locator('#stage-filter').selectOption('KEEP_WARM')
await setAsOf(BEFORE)
await shot('01-not-due-day-before', { clip: { x: 0, y: 0, width: 1440, height: 640 } })

// ---- 2. the date arrives: due -------------------------------------------
await setAsOf(DUE)
await shot('02-due-on-the-date', { clip: { x: 0, y: 0, width: 1440, height: 640 } })

// ---- 3. the KPI, and clicking it filters --------------------------------
await page.locator('#stage-filter').selectOption('')
await page.waitForTimeout(700)
await page.getByRole('button', { name: /Re-engagement Due/ }).click()
await page.waitForTimeout(900)
await shot('03-due-kpi-filters-queue', { clip: { x: 0, y: 0, width: 1440, height: 640 } })

// ---- 4. the Re-engage action on the founder detail ----------------------
await page.goto(`${BASE}/#/founders/${FID}`, { waitUntil: 'networkidle' })
await page.waitForSelector('#human-heading')
await page.locator('#as-of-founder').fill(DUE)      // read-time lens: the date has arrived
await page.waitForTimeout(900)
await page.evaluate(() => {
  const el = document.querySelector('#human-heading')
  window.scrollTo({ top: (el?.getBoundingClientRect().top ?? 0) + window.scrollY - 20 })
})
await shot('04-reengage-action', { clip: { x: 0, y: 0, width: 1440, height: 620 } })

// ---- 5. perform it: one human act, with a reason ------------------------
await page.getByTestId('reengage-button').click()
await page.locator('#stage-reason').fill('keep-warm date reached — re-engaging for a call')
await page.getByRole('button', { name: 'Move stage' }).click()
await page.waitForTimeout(1200)
await page.evaluate(() => {
  const el = document.querySelector('#human-heading')
  window.scrollTo({ top: (el?.getBoundingClientRect().top ?? 0) + window.scrollY - 20 })
})
await shot('05-post-reengage-nurturing', { clip: { x: 0, y: 0, width: 1440, height: 620 } })

// ---- 6. audit history ----------------------------------------------------
await page.evaluate(() => {
  const el = document.querySelector('#audit-heading')
  window.scrollTo({ top: (el?.getBoundingClientRect().top ?? 0) + window.scrollY - 20 })
})
await shot('06-audit-after-reengage')

// ---- 7. no longer due ----------------------------------------------------
await page.goto(`${BASE}/#/`, { waitUntil: 'networkidle' })
await page.waitForSelector('table')
await setAsOf(DUE)
await page.getByRole('button', { name: /Re-engagement Due/ }).click()
await page.waitForTimeout(900)
await shot('07-no-longer-due', { clip: { x: 0, y: 0, width: 1440, height: 620 } })

// ---- 8. stuck dashboard at a simulated date -----------------------------
await page.goto(`${BASE}/#/pipeline`, { waitUntil: 'networkidle' })
await page.waitForSelector('#dashboard-heading')
await page.locator('#as-of-pipeline').fill(DUE)
await page.waitForTimeout(1200)
await page.evaluate(() => {
  const el = document.querySelector('#dashboard-heading')
  window.scrollTo({ top: (el?.getBoundingClientRect().top ?? 0) + window.scrollY - 20 })
})
await shot('08-stuck-and-simulated-dashboard')

await b.close()
fs.writeFileSync(`${OUT}/ui-transcript.log`, log.join('\n'))
fs.writeFileSync(`${OUT}/console.log`, console_log.join('\n') || '(none)')
console.log('\nmutations:', log.filter((l) => !l.startsWith('SHOT')).join(' | ') || 'none')
console.log('console:', console_log.length, console_log.join(' | '))
