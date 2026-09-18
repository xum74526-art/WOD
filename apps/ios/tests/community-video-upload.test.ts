import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

test('first-review community publisher exposes text only', () => {
  const api = readFileSync(new URL('../src/api/community.ts', import.meta.url), 'utf8')
  const publish = readFileSync(new URL('../src/pages/community/publish.vue', import.meta.url), 'utf8')

  assert.match(api, /uploadCommunityMedia\(filePath: string, onProgress\?/)
  assert.match(publish, /createPost\(\{/)
  assert.match(publish, /content: form\.content/)
  assert.match(publish, /topic: form\.topic/)
  assert.doesNotMatch(publish, /uploadCommunityMedia|uni\.chooseImage|uni\.chooseVideo/)
  assert.doesNotMatch(publish, /images:|video:|video_duration:/)
  assert.doesNotMatch(publish, /type === ['"](?:image|video)['"]/)
})
