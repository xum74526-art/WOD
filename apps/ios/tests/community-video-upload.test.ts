import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

test('iOS accepts common source containers but publishes only server-standardized MP4', () => {
  const api = readFileSync(new URL('../src/api/community.ts', import.meta.url), 'utf8')
  const publish = readFileSync(new URL('../src/pages/community/publish.vue', import.meta.url), 'utf8')
  const locale = readFileSync(new URL('../src/store/i18n.ts', import.meta.url), 'utf8')

  assert.match(api, /duration\?: number \| null/)
  assert.match(api, /standardized\?: boolean/)
  assert.match(api, /timeout: 240000/)
  assert.match(publish, /extension: \['mp4', 'mov', 'webm'\]/)
  assert.match(publish, /result\.content_type !== 'video\/mp4'/)
  assert.match(publish, /!result\.standardized/)
  assert.match(publish, /item\.duration = Math\.max\(1, Math\.round\(Number\(result\.duration\)\)\)/)
  assert.match(publish, /Number\(res\.duration \|\| 0\) > 300/)
  assert.match(locale, /上传后统一转换为兼容 MP4；最长 5 分钟，不超过 20MB/)
})

test('iOS upload UX distinguishes byte transfer from server processing', () => {
  const request = readFileSync(new URL('../src/api/request.ts', import.meta.url), 'utf8')
  const api = readFileSync(new URL('../src/api/community.ts', import.meta.url), 'utf8')
  const publish = readFileSync(new URL('../src/pages/community/publish.vue', import.meta.url), 'utf8')

  assert.match(request, /onProgress\?: \(progress: number\) => void/)
  assert.match(request, /task\.onProgressUpdate/)
  assert.match(api, /uploadCommunityMedia\(filePath: string, onProgress\?/)
  assert.match(publish, /type UploadStatus = 'uploading' \| 'processing' \| 'ready' \| 'failed'/)
  assert.match(publish, /progress >= 100 \? 'processing' : 'uploading'/)
  assert.match(publish, /mediaUploadingProgress/)
  assert.match(publish, /mediaProcessing/)
})
