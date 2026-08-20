import { chromium } from 'file:///C:/Users/ASUS/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs'

const browser = await chromium.launch({
  headless: true,
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
})
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
const page = await context.newPage()

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

await page.goto('http://127.0.0.1:9100/login', { waitUntil: 'networkidle' })
await page.getByRole('tab', { name: '邮箱' }).click()
assert(await page.getByText('邮箱', { exact: true }).count() >= 2, '邮箱登录表单没有显示')

await page.getByRole('tab', { name: '手机号' }).click()
await page.getByRole('textbox', { name: '手机号' }).fill('13900000000')
await page.getByLabel('密码').fill('test-password')
await page.getByRole('button', { name: '手机号登录' }).click()
await page.getByText(/短信服务尚未配置/).waitFor()

await page.getByRole('tab', { name: 'Kai' }).click()
await page.getByRole('button', { name: /继续使用 Kai/ }).waitFor()
await page.getByText(/不会接收或保存你的 Kai 密码/).waitFor()

await page.goto('http://127.0.0.1:9100/register', { waitUntil: 'networkidle' })
await page.getByRole('tab', { name: '邮箱' }).click()
await page.getByLabel('称呼').fill('网站验收用户')
await page.getByRole('textbox', { name: '邮箱', exact: true }).fill(`qa-${Date.now()}@example.com`)
await page.getByLabel('设置密码').fill('qa-secure-password')
await page.getByRole('button', { name: '邮箱注册' }).click()
await page.waitForURL('**/account')
await page.getByText(/欢迎回来/).waitFor()

console.log('Auth UI checks passed: phone disabled state, Kai entry, real email session and account redirect.')
await browser.close()
