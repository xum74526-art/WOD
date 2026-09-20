import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

import { ensureClientRequestIntent } from '../src/utils/client-request-intent.ts'

function compileCommunityApi() {
  const source = readFileSync(new URL('../src/api/community.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
  const exports: Record<string, any> = {}
  const calls: Array<Record<string, unknown>> = []
  const request = (options: Record<string, unknown>) => {
    calls.push(options)
    return Promise.resolve({ id: 11, post_id: 7, user_id: 3, content: 'same comment', post_comments: 9 })
  }
  new Function('require', 'exports', compiled)(
    (name: string) => {
      if (name === './request') return { request, upload: () => Promise.resolve({}) }
      throw new Error(`Unexpected dependency: ${name}`)
    },
    exports,
  )
  return { createComment: exports.createComment as (id: number, content: string, requestId: string) => Promise<unknown>, calls }
}

test('community comment intent reuses its request id until post or content changes', () => {
  let sequence = 0
  const createRequestId = () => `community-comment-${++sequence}`
  const payload = { post_id: 7, content: 'same comment' }
  const first = ensureClientRequestIntent(null, payload, createRequestId)
  const retry = ensureClientRequestIntent(first, { ...payload }, createRequestId)

  assert.equal(retry.requestId, first.requestId)
  assert.equal(sequence, 1)
  const changedContent = ensureClientRequestIntent(retry, { ...payload, content: 'edited comment' }, createRequestId)
  assert.notEqual(changedContent.requestId, first.requestId)
  const changedPost = ensureClientRequestIntent(changedContent, { post_id: 8, content: 'edited comment' }, createRequestId)
  assert.notEqual(changedPost.requestId, changedContent.requestId)
  const afterSuccess = ensureClientRequestIntent(null, payload, createRequestId)
  assert.notEqual(afterSuccess.requestId, first.requestId)
  const editedWhileInFlight = { ...payload, content: 'edited while in flight' }
  assert.notEqual(JSON.stringify(editedWhileInFlight), first.signature)
  const restoredWhileInFlight = { ...payload, content: 'same comment' }
  assert.equal(JSON.stringify(restoredWhileInFlight), first.signature)
  assert.notEqual(ensureClientRequestIntent(null, restoredWhileInFlight, createRequestId).requestId, first.requestId)
})

test('community comment API sends one stable request id and opts into one uncertain retry', async () => {
  const api = compileCommunityApi()
  const result = await api.createComment(7, 'same comment', 'community-comment-request-1')

  assert.deepEqual(result, { id: 11, post_id: 7, user_id: 3, content: 'same comment', post_comments: 9 })
  assert.deepEqual(api.calls, [{
    url: '/community/posts/7/comments',
    method: 'POST',
    data: { content: 'same comment', client_request_id: 'community-comment-request-1' },
    retryUncertainOnce: true,
  }])
})

test('community detail locks rapid taps, preserves edited text, and upserts by comment id', () => {
  const page = readFileSync(new URL('../src/pages/community/detail.vue', import.meta.url), 'utf8')
  const start = page.indexOf('async function onComment')
  const flow = page.slice(start, page.indexOf('</script>', start))

  assert.ok(start >= 0)
  assert.match(page, /let commentInFlight = false/)
  assert.doesNotMatch(page, /watch\(\[pid, commentText\]/)
  assert.match(flow, /const postId = pid\.value\s+const content = commentText\.value\.trim\(\)/)
  assert.match(flow, /if \(!postId \|\| !content \|\| commentInFlight\) return/)
  assert.match(flow, /\{ post_id: postId, content \}/)
  assert.match(flow, /pendingCommentIntent\.value = intent\s+commentInFlight = true/)
  assert.match(flow, /await createComment\(postId, content, intent\.requestId\)/)
  assert.match(flow, /if \(pendingCommentIntent\.value === intent\) pendingCommentIntent\.value = null\s+const submittedDraftStillCurrent/)
  assert.match(flow, /if \(submittedDraftStillCurrent\) commentText\.value = ''/)
  assert.match(flow, /comments\.value = \[c, \.\.\.comments\.value\.filter\(item => item\.id !== c\.id\)\]/)
  assert.match(flow, /typeof c\.post_comments === 'number'/)
  assert.match(flow, /finally \{ commentInFlight = false \}/)
  assert.equal(flow.match(/pendingCommentIntent\.value = null/g)?.length, 1)
  assert.doesNotMatch(flow, /comments\.value\.unshift|post\.value\.comments\+\+/)
})
