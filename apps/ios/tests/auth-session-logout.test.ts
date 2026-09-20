import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { signOutCurrentDevice } from '../src/utils/session-logout.ts'

const readSource = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('explicit sign-out revokes the server session before clearing local auth', () => {
  const api = readSource('../src/api/user.ts')
  const request = readSource('../src/api/request.ts')
  const store = readSource('../src/store/user.ts')
  const settings = readSource('../src/pages/settings/index.vue')
  const password = readSource('../src/pages/password/index.vue')

  assert.match(api, /function logoutCurrentSession\(\)[\s\S]*url: '\/auth\/logout', method: 'POST',[\s\S]*unauthorized: 'reject'/)
  assert.match(request, /options\.auth === 'none' \|\| options\.unauthorized === 'reject'/)
  const signOut = store.slice(store.indexOf('function signOut()'), store.indexOf('const isLogin'))
  assert.match(signOut, /signOutCurrentDevice\(userApi\.logoutCurrentSession, logout\)/)
  assert.match(settings, /void userStore.signOut\(\)[\s\S]*uni.reLaunch\(\{ url: '\/pages\/login\/index' \}\)/)
  assert.match(password, /await userApi.changePassword[\s\S]*void userStore.signOut\(\)[\s\S]*修改成功/)
})

test('local logout is immediate and remote failures are contained', async () => {
  let finish!: () => void
  const events: string[] = []
  const pending = new Promise<void>((resolve) => { finish = resolve })
  const result = signOutCurrentDevice(
    () => { events.push('remote-started'); return pending },
    () => { events.push('local-cleared') },
  )
  assert.deepEqual(events, ['remote-started', 'local-cleared'])
  finish()
  await result

  let cleared = false
  await signOutCurrentDevice(
    () => Promise.reject(new Error('offline')),
    () => { cleared = true },
  )
  assert.equal(cleared, true)
})
