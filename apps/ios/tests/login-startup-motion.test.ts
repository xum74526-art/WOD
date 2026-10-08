import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

function compile(source: string) {
  return ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
}

function clock() {
  let id = 0
  const timers = new Map<number, { run: () => void; delay: number }>()
  return {
    timers,
    setTimeout(run: () => void, delay: number) { timers.set(++id, { run, delay }); return id },
    clearTimeout(key: number) { timers.delete(key) },
    flush(delay: number) {
      for (const [key, timer] of [...timers]) {
        if (timer.delay === delay) { timers.delete(key); timer.run() }
      }
    },
  }
}

test('native splash closes once after page readiness and cancels its fallback', () => {
  const source = readFileSync(new URL('../src/utils/app-launch.ts', import.meta.url), 'utf8')
  const exports: Record<string, any> = {}
  const timer = clock()
  let closed = 0
  new Function('exports', 'plus', 'setTimeout', 'clearTimeout', compile(source))(
    exports, { navigator: { closeSplashscreen: () => { closed++ } } }, timer.setTimeout, timer.clearTimeout,
  )
  exports.beginAppLaunch()
  exports.beginAppLaunch()
  assert.equal(timer.timers.size, 1)
  assert.equal(closed, 0)
  exports.finishAppLaunch()
  exports.finishAppLaunch()
  assert.equal(closed, 1)
  assert.equal(timer.timers.size, 0)
})

test('a failed startup cannot trap the user behind the native splash', () => {
  const source = readFileSync(new URL('../src/utils/app-launch.ts', import.meta.url), 'utf8')
  const exports: Record<string, any> = {}
  const timer = clock()
  let closed = 0
  new Function('exports', 'plus', 'setTimeout', 'clearTimeout', compile(source))(
    exports, { navigator: { closeSplashscreen: () => { closed++ } } }, timer.setTimeout, timer.clearTimeout,
  )
  exports.beginAppLaunch()
  timer.flush(8000)
  exports.finishAppLaunch()
  assert.equal(closed, 1)
})

function loginFixture(opacities: number[] = [1], reducedMotion = false) {
  const source = readFileSync(new URL('../src/pages/login/index.vue', import.meta.url), 'utf8')
  const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)![1]
  const hooks: Record<string, Array<() => void>> = {}
  const timer = clock()
  const navigated: string[] = []
  let restoreResolve: (() => void) | undefined
  let loginResolve: (() => void) | undefined
  let loginReject: ((error: Error) => void) | undefined
  let logins = 0
  let coverCloses = 0
  const user = {
    isLogin: false,
    authReady: false,
    restore: () => new Promise<void>((resolve) => { restoreResolve = resolve }),
    login: () => { logins++; return new Promise<void>((resolve, reject) => { loginResolve = resolve; loginReject = reject }) },
  }
  const query: Record<string, any> = {}
  for (const key of ['in', 'select', 'exec']) query[key] = () => query
  query.boundingClientRect = (callback: (value: unknown) => void) => { callback({ height: 250 }); return query }
  query.fields = (_fields: unknown, callback: (value: unknown) => void) => {
    callback({ opacity: String(opacities.length > 1 ? opacities.shift() : opacities[0]) })
    return query
  }
  const uni = { getStorageSync: () => '', showToast: () => {}, createSelectorQuery: () => query, $off: () => {} }
  const requireMock = (name: string) => {
    if (name === 'vue') return {
      ref: (value: unknown) => ({ value }), reactive: (value: unknown) => value,
      getCurrentInstance: () => ({ proxy: {} }), nextTick: (fn: () => void) => Promise.resolve().then(fn),
      watch: () => {}, onMounted: () => {},
      onUnmounted: (fn: () => void) => { (hooks.unmounted ??= []).push(fn) },
    }
    if (name === '@dcloudio/uni-app') return Object.fromEntries(
      ['onHide', 'onLoad', 'onReady', 'onResize', 'onShow'].map((key) =>
        [key, (fn: () => void) => { (hooks[key] ??= []).push(fn) }]),
    )
    if (name === '@/store/user') return { useUserStore: () => user }
    if (name === '@/api/request') return { request: () => { throw new Error('Unexpected network call') } }
    if (name === '@/api/user') return {}
    if (name === '@/store/i18n') return { useI18nStore: () => ({ t: (key: string) => key }) }
    if (name === '@/utils/app-launch') return { finishAppLaunch: () => { coverCloses++ } }
    if (name === '@/utils/motion') return { prefersReducedMotion: () => reducedMotion }
    if (name === '@/utils/nav') return { switchTab: (url: string) => navigated.push(url) }
    if (name === '@/utils/auth-return-path') return { consumeAuthReturnPath: () => null }
    if (name === '@/utils/inquiry-request') return { hasInquiryRequestPrefill: () => false }
    if (name === '@/utils/account-deletion-receipt') return { readDeletionReceipt: () => null }
    if (name === '@/utils/login-kai-callback') return { clearPendingLoginKaiCallback: () => {}, peekPendingLoginKaiCallback: () => null }
    if (name === '@/utils/kai-auth-callback') return { parseKaiAuthUrl: () => null }
    throw new Error('Unexpected dependency: ' + name)
  }
  const view = new Function('require', 'exports', 'uni', 'plus', 'setTimeout', 'clearTimeout',
    compile(script) + '\nreturn { pageEntered, submitting, loginSucceeded, form, agree, mode, authMethod, setMode, setAuthMethod, submit };')(
    requireMock, {}, uni, { runtime: { arguments: '' } }, timer.setTimeout, timer.clearTimeout,
  )
  return {
    view, user, hooks, timer, navigated,
    logins: () => logins, coverCloses: () => coverCloses,
    resolveRestore: () => restoreResolve!(), resolveLogin: () => loginResolve!(),
    rejectLogin: () => loginReject!(new Error('Login failed')),
  }
}

test('login enters only after ready; returning from recovery/background never hides it again', async () => {
  const f = loginFixture()
  assert.equal(f.view.pageEntered.value, false)
  f.hooks.onReady.forEach((hook) => hook())
  assert.equal(f.coverCloses(), 0)
  f.timer.flush(32)
  await Promise.resolve()
  assert.equal(f.coverCloses(), 1)
  assert.equal(f.view.pageEntered.value, true)
  f.hooks.onHide.forEach((hook) => hook())
  f.hooks.onShow.forEach((hook) => hook())
  await Promise.resolve()
  assert.equal(f.view.pageEntered.value, true)
})

test('native cover remains until the view layer reports a visible login form', async () => {
  const f = loginFixture([0, 0.2, 0.6])
  f.hooks.onReady.forEach((hook) => hook())
  f.timer.flush(32)
  await Promise.resolve()
  assert.equal(f.coverCloses(), 0)
  f.timer.flush(40)
  await Promise.resolve()
  assert.equal(f.coverCloses(), 0)
  f.timer.flush(40)
  await Promise.resolve()
  assert.equal(f.coverCloses(), 1)
})

test('missing computed style cannot keep the native cover open indefinitely', async () => {
  const f = loginFixture([0])
  f.hooks.onReady.forEach((hook) => hook())
  f.timer.flush(32)
  await Promise.resolve()
  for (let attempt = 0; attempt < 12; attempt++) {
    f.timer.flush(40)
    await Promise.resolve()
  }
  assert.equal(f.coverCloses(), 1)
  assert.equal(f.timer.timers.size, 0)
})

test('unmount stops pending visibility probes without affecting the next page', async () => {
  const f = loginFixture([0])
  f.hooks.onReady.forEach((hook) => hook())
  f.timer.flush(32)
  await Promise.resolve()
  assert.equal(f.timer.timers.size, 1)
  f.hooks.unmounted.forEach((hook) => hook())
  assert.equal(f.timer.timers.size, 0)
  f.timer.flush(40)
  await Promise.resolve()
  assert.equal(f.coverCloses(), 0)
})

test('an expired stored session cannot schedule the old delayed home redirect', async () => {
  const f = loginFixture()
  f.user.isLogin = true
  f.hooks.onShow.forEach((hook) => hook())
  assert.deepEqual(f.navigated, [])
  f.user.isLogin = false
  f.user.authReady = true
  f.resolveRestore()
  await Promise.resolve()
  assert.deepEqual(f.navigated, [])
  assert.equal([...f.timer.timers.values()].some((timer) => timer.delay === 800), false)
})

test('a verified restored session navigates once only after restoration completes', async () => {
  const f = loginFixture()
  f.user.isLogin = true
  f.hooks.onShow.forEach((hook) => hook())
  assert.deepEqual(f.navigated, [])
  f.user.authReady = true
  f.resolveRestore()
  await Promise.resolve()
  assert.deepEqual(f.navigated, ['/pages/index/index'])
  f.hooks.onShow.forEach((hook) => hook())
  f.resolveRestore()
  await Promise.resolve()
  assert.deepEqual(f.navigated, ['/pages/index/index'])
})

test('a late session restoration does not interrupt a page opened from login', async () => {
  const f = loginFixture()
  f.user.isLogin = true
  f.hooks.onShow.forEach((hook) => hook())
  f.hooks.onHide.forEach((hook) => hook())
  f.user.authReady = true
  f.resolveRestore()
  await Promise.resolve()
  assert.deepEqual(f.navigated, [])
})

test('login blocks repeat submission and mode changes until success navigation completes', async () => {
  const f = loginFixture()
  f.view.agree.value = true
  f.view.form.phone = '13800000000'
  f.view.form.password = 'fixture-password'
  const pending = f.view.submit()
  await f.view.submit()
  f.view.setMode('register')
  f.view.setAuthMethod('kai')
  assert.equal(f.logins(), 1)
  assert.equal(f.view.mode.value, 'login')
  assert.equal(f.view.authMethod.value, 'phone')
  f.user.isLogin = true
  f.user.authReady = true
  f.resolveLogin()
  await pending
  assert.equal(f.view.loginSucceeded.value, true)
  await f.view.submit()
  assert.equal(f.logins(), 1)
  f.timer.flush(520)
  assert.deepEqual(f.navigated, ['/pages/index/index'])
})

test('unmount clears entrance and success timers so an old login cannot redirect later', async () => {
  const f = loginFixture()
  f.hooks.onReady.forEach((hook) => hook())
  f.view.agree.value = true
  f.view.form.phone = '13800000000'
  f.view.form.password = 'fixture-password'
  const pending = f.view.submit()
  f.user.isLogin = true
  f.user.authReady = true
  f.resolveLogin()
  await pending
  assert.equal(f.timer.timers.size, 2)
  f.hooks.unmounted.forEach((hook) => hook())
  assert.equal(f.timer.timers.size, 0)
  f.timer.flush(520)
  assert.deepEqual(f.navigated, [])
})

test('a failed request releases the loading button without success or navigation', async () => {
  const f = loginFixture()
  f.view.agree.value = true
  f.view.form.phone = '13800000000'
  f.view.form.password = 'fixture-password'
  const pending = f.view.submit()
  assert.equal(f.view.submitting.value, true)
  assert.equal(f.view.loginSucceeded.value, false)
  f.rejectLogin()
  await pending
  assert.equal(f.view.submitting.value, false)
  assert.equal(f.view.loginSucceeded.value, false)
  assert.equal(f.timer.timers.size, 0)
  assert.deepEqual(f.navigated, [])
  // An error must leave the form editable and allow another attempt.
  f.view.setAuthMethod('kai')
  assert.equal(f.view.authMethod.value, 'kai')
})

test('reduced motion skips the success animation wait after a verified login', async () => {
  const f = loginFixture([1], true)
  f.view.agree.value = true
  f.view.form.phone = '13800000000'
  f.view.form.password = 'fixture-password'
  const pending = f.view.submit()
  f.user.isLogin = true
  f.user.authReady = true
  f.resolveLogin()
  await pending
  f.timer.flush(0)
  assert.deepEqual(f.navigated, ['/pages/index/index'])
  assert.equal(f.timer.timers.size, 0)
})

test('login completing in the background waits until the page is visible', async () => {
  const f = loginFixture()
  f.view.agree.value = true
  f.view.form.phone = '13800000000'
  f.view.form.password = 'fixture-password'
  const pending = f.view.submit()
  f.hooks.onHide.forEach((hook) => hook())
  f.user.isLogin = true
  f.user.authReady = true
  f.resolveLogin()
  await pending
  assert.equal(f.timer.timers.size, 0)
  assert.deepEqual(f.navigated, [])
  f.hooks.onShow.forEach((hook) => hook())
  f.timer.flush(520)
  assert.deepEqual(f.navigated, ['/pages/index/index'])
})

test('hiding the success state cancels its navigation until returning', async () => {
  const f = loginFixture()
  f.view.agree.value = true
  f.view.form.phone = '13800000000'
  f.view.form.password = 'fixture-password'
  const pending = f.view.submit()
  f.user.isLogin = true
  f.user.authReady = true
  f.resolveLogin()
  await pending
  f.hooks.onHide.forEach((hook) => hook())
  f.timer.flush(520)
  assert.deepEqual(f.navigated, [])
  f.hooks.onShow.forEach((hook) => hook())
  f.timer.flush(520)
  assert.deepEqual(f.navigated, ['/pages/index/index'])
})
