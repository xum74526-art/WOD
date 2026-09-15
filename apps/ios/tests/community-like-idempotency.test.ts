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
    return Promise.resolve({ liked: true, likes: 9 })
  }
  new Function('require', 'exports', compiled)(
    (name: string) => {
      if (name === './request') return { request, upload: () => Promise.resolve({}) }
      throw new Error(`Unexpected dependency: ${name}`)
    },
    exports,
  )
  return { setLike: exports.setLike as (id: number, liked: boolean) => Promise<unknown>, calls }
}

function functionFlow(relative: string, name: string, nextName: string) {
  const page = readFileSync(new URL(relative, import.meta.url), 'utf8')
  const start = page.indexOf(`async function ${name}`)
  const end = page.indexOf(nextName, start)
  assert.ok(start >= 0 && end > start)
  return page.slice(start, end)
}

test('community like API submits an explicit state and opts into one safe retry', async () => {
  const api = compileCommunityApi()
  assert.deepEqual(await api.setLike(7, true), { liked: true, likes: 9 })
  assert.deepEqual(api.calls, [{
    url: '/community/posts/7/like',
    method: 'POST',
    data: { liked: true },
    retryUncertainOnce: true,
  }])
})

test('community list locks each post and applies only the server response', () => {
  const flow = functionFlow('../src/pages/community/index.vue', 'onLike', 'function onShare')
  const target = flow.indexOf('const targetLiked = !d.is_liked')
  const request = flow.indexOf('await setLike(d.id, targetLiked)')
  const resolveCurrent = flow.indexOf('const current = list.value.find(item => item.id === d.id)')
  const apply = flow.indexOf('current.is_liked = res.liked')

  assert.match(flow, /if \(likeInFlight\.has\(d\.id\)\) return/)
  assert.match(flow, /likeInFlight\.add\(d\.id\)/)
  assert.ok(target >= 0 && target < request)
  assert.ok(request < resolveCurrent && resolveCurrent < apply)
  assert.match(flow, /if \(!current\) return/)
  assert.doesNotMatch(flow, /d\.is_liked = res\.liked/)
  assert.match(flow, /finally \{ likeInFlight\.delete\(d\.id\) \}/)
})

test('community detail holds one like request at a time and always releases it', () => {
  const flow = functionFlow('../src/pages/community/detail.vue', 'onLike', 'async function onFollow')
  const target = flow.indexOf('const targetLiked = !post.value.is_liked')
  const lock = flow.indexOf('likeInFlight = true')
  const request = flow.indexOf('await setLike(pid.value, targetLiked)')
  const apply = flow.indexOf('post.value.is_liked = res.liked')

  assert.match(flow, /if \(!post\.value \|\| likeInFlight\) return/)
  assert.ok(target >= 0 && target < lock && lock < request)
  assert.ok(request < apply)
  assert.match(flow, /finally \{ likeInFlight = false \}/)
})
