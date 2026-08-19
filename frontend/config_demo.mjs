/** CP8 evidence: config change → PUT (no rescore) → explicit Recalculate. */
import { chromium } from 'playwright'
import fs from 'node:fs'

const OUT = '/Users/piyushchandra/founder-engagement/docs/cp8'
const BASE = 'http://localhost:5173'
const DEMO = '021ceb3f-a1ba-4508-89e1-5f8e2feed1da'
const log = []
const console_log = []

const run = async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  page.on('console', (m) => console_log.push(`[${m.type()}] ${m.text()}`))
  page.on('pageerror', (e) => console_log.push(`[pageerror] ${e.message}`))
  page.on('response', (r) => {
    if (r.url().includes('/api/') && ['POST', 'PUT', 'PATCH'].includes(r.request().method())) {
      log.push(`${r.request().method()} ${r.url().replace('/api', '')} -> ${r.status()}`)
    }
  })

  await page.goto(`${BASE}/#/pipeline`, { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: 'Configuration' }).click()
  await page.waitForSelector('#config-heading')

  await page.locator('#threshold-priority_broad').fill('55')
  await page.locator('#health-industries').fill(
    ['Hospital & Health Care', 'Health, Wellness and Fitness', 'Medical Devices',
     'Mental Health Care', 'Biotechnology', 'Pharmaceuticals'].join('\n'))
  await page.getByRole('button', { name: 'Save configuration' }).click()
  await page.waitForSelector('text=older rubric')
  await page.screenshot({ path: `${OUT}/17-config-saved-not-rescored.png` })
  log.push('SHOT 17-config-saved-not-rescored')

  // the founder detail must now say the stored assessment is stale
  const detail = await browser.newPage({ viewport: { width: 1440, height: 700 } })
  await detail.goto(`${BASE}/#/founders/${DEMO}`, { waitUntil: 'networkidle' })
  await detail.waitForSelector('text=Assessment needs recalculation')
  await detail.screenshot({ path: `${OUT}/18-stale-rubric-indicator.png`,
                            clip: { x: 0, y: 90, width: 1440, height: 520 } })
  log.push('SHOT 18-stale-rubric-indicator')

  // explicit recalculation
  await page.getByRole('button', { name: 'Recalculate assessments' }).click()
  await page.waitForSelector('text=Recalculated', { timeout: 60000 })
  await page.screenshot({ path: `${OUT}/19-explicit-recalculate.png` })
  log.push('SHOT 19-explicit-recalculate')

  await detail.reload({ waitUntil: 'networkidle' })
  await detail.waitForSelector('#assessment-heading')
  await detail.screenshot({ path: `${OUT}/20-after-recalculate-metadata.png`,
                            clip: { x: 0, y: 90, width: 1440, height: 520 } })
  log.push('SHOT 20-after-recalculate-metadata')

  await detail.locator('#audit-heading').scrollIntoViewIfNeeded()
  await detail.waitForTimeout(400)
  await detail.screenshot({ path: `${OUT}/21-audit-rescore-vs-human.png` })
  log.push('SHOT 21-audit-rescore-vs-human')

  await browser.close()
  fs.appendFileSync(`${OUT}/ui-transcript.log`,
    '\n--- CONFIG / RESCORE DEMO ---\n' + log.join('\n'))
  fs.appendFileSync(`${OUT}/console.log`, '\n--- config demo ---\n' + console_log.join('\n'))
  console.log(log.join('\n'))
  console.log('console:', console_log.length, console_log.join(' | '))
}
run().catch((e) => { console.error(e); process.exit(1) })
