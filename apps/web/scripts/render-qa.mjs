import { chromium } from 'file:///C:/Users/ASUS/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs'
import fs from 'node:fs/promises'
import path from 'node:path'

const browser = await chromium.launch({
  headless: true,
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
})

const cases = [
  { name: 'home-desktop', route: '/', width: 1440, height: 1000, scheme: 'light', fullPage: true },
  { name: 'login-desktop', route: '/login', width: 1440, height: 1000, scheme: 'light' },
  { name: 'register-desktop', route: '/register', width: 1440, height: 1000, scheme: 'light' },
  { name: 'market-desktop', route: '/market', width: 1440, height: 1000, scheme: 'light', fullPage: true },
  { name: 'community-desktop', route: '/community', width: 1440, height: 1000, scheme: 'light', fullPage: true },
  { name: 'supplier-apply-desktop', route: '/supplier/apply', width: 1440, height: 1000, scheme: 'light', fullPage: true },
  { name: 'home-mobile', route: '/', width: 390, height: 844, scheme: 'light', fullPage: true },
  { name: 'login-mobile', route: '/login', width: 390, height: 844, scheme: 'light', fullPage: true },
  { name: 'register-mobile', route: '/register', width: 390, height: 844, scheme: 'light', fullPage: true },
  { name: 'market-mobile', route: '/market', width: 390, height: 844, scheme: 'light', fullPage: true },
  { name: 'account-leases-mobile', route: '/account/leases', width: 390, height: 844, scheme: 'light', fullPage: true },
  { name: 'home-dark', route: '/', width: 1440, height: 1000, scheme: 'dark' },
  { name: 'login-dark', route: '/login', width: 1440, height: 1000, scheme: 'dark' },
]

const reports = []

for (const testCase of cases) {
  const context = await browser.newContext({
    viewport: { width: testCase.width, height: testCase.height },
    deviceScaleFactor: 1,
    colorScheme: testCase.scheme,
  })
  const page = await context.newPage()
  const errors = []
  const failedResponses = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('response', (response) => {
    if (response.status() >= 400) {
      failedResponses.push({ status: response.status(), url: response.url() })
    }
  })
  await page.goto(`http://127.0.0.1:9100${testCase.route}`, { waitUntil: 'networkidle' })
  const dimensions = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    scrollHeight: document.documentElement.scrollHeight,
  }))
  await page.screenshot({
    path: path.resolve('qa', `${testCase.name}.png`),
    fullPage: Boolean(testCase.fullPage),
  })
  reports.push({ ...testCase, ...dimensions, errors, failedResponses })
  await context.close()
}

await fs.writeFile(path.resolve('qa', 'report.json'), JSON.stringify(reports, null, 2))
await browser.close()
