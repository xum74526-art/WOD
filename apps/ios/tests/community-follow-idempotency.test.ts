import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

function compileCommunityApi() {
  const source = readFileSync(new URL('../src/api/community.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
  const exports: Record<string, any> = {}
  const calls: Array<Record<string, unknown>> = []
  const request = (options: Record<string, unknown>) => {
    calls.push(options)
    return Promise.resolve({ following: true })
  }
  new Function('require', 'exports', compiled)(
    (name: string) => {
      if (name === './request') return { request, upload: () => Promise.resolve({}) }
      throw new Error(`Unexpected dependency: ${name}`)
    },
    exports,
  )
  return { setFollow: exports.setFollow as (id: number, following: boolean) => Promise<unknown>, calls }
}

function functionFlow(relative: string, name: string, nextName: string) {
  const page = readFileSync(new URL(relative, import.meta.url), 'utf8')
  const start = page.indexOf(`async function ${name}`)
  const end = page.indexOf(nextName, start)
  assert.ok(start >= 0 && end > start)
  return page.slice(start, end)
}

test('community follow API submits an explicit state and opts into one safe retry', async () => {
  const api = compileCommunityApi()
  assert.deepEqual(await api.setFollow(8, true), { following: true })
  assert.deepEqual(api.calls, [{
    url: '/community/users/8/follow',
    method: 'POST',
    data: { following: true },
    retryUncertainOnce: true,
  }])
})

test('community list locks by user and applies the server state to every current post', () => {
  const flow = functionFlow('../src/pages/community/index.vue', 'onFollow', 'function goPublish')
  const target = flow.indexOf('const targetFollowing = !d.is_following')
  const request = flow.indexOf('await setFollow(d.user_id, targetFollowing)')
  const apply = flow.indexOf('if (p.user_id === d.user_id) p.is_following = res.following')

  assert.match(flow, /if \(followInFlight\.has\(d\.user_id\)\) return/)
  assert.match(flow, /followInFlight\.add\(d\.user_id\)/)
  assert.ok(target >= 0 && target < request)
  assert.ok(request < apply)
  assert.match(flow, /finally \{ followInFlight\.delete\(d\.user_id\) \}/)
})

test('community detail holds one follow request at a time and always releases it', () => {
  const flow = functionFlow('../src/pages/community/detail.vue', 'onFollow', 'function onShare')
  const target = flow.indexOf('const targetFollowing = !post.value.is_following')
  const lock = flow.indexOf('followInFlight = true')
  const request = flow.indexOf('await setFollow(post.value.user_id, targetFollowing)')
  const apply = flow.indexOf('post.value.is_following = res.following')

  assert.match(flow, /if \(!post\.value \|\| followInFlight\) return/)
  assert.ok(target >= 0 && target < lock && lock < request)
  assert.ok(request < apply)
  assert.match(flow, /finally \{ followInFlight = false \}/)
})
