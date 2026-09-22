import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

function read(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

test('major announcement uses the public endpoint and opens as a home modal', () => {
  const api = read('../src/api/notification.ts')
  const home = read('../src/pages/index/index.vue')

  assert.match(api, /'major_announcement' \| 'system'/)
  assert.match(api, /url: '\/notifications\/major-announcement'/)
  assert.match(api, /auth: 'none'/)
  assert.ok(home.indexOf('<HomePromoCarousel />') < home.indexOf('class="major-announcement-overlay"'))
  assert.match(home, /kai-major-announcement-dismissed:v2:\$\{user\.value\?\.id/)
  assert.match(home, /loadMajorAnnouncement\(\)/)
  assert.match(home, /dismissMajorAnnouncement/)
  assert.match(home, /role="dialog" aria-modal="true"/)
  assert.match(home, /acknowledgeMajorAnnouncement/)
  assert.match(home, /majorAnnouncementPublishedAt/)
})

test('notification center exposes the major-announcement category', () => {
  const page = read('../src/pages/notifications/index.vue')
  const i18n = read('../src/store/i18n.ts')

  assert.match(page, /value: 'major_announcement', label: 'majorAnnouncement'/)
  assert.match(page, /major_announcement: 'majorAnnouncement'/)
  assert.match(i18n, /majorAnnouncement: '重大公告'/)
  assert.match(i18n, /acknowledgeMajorAnnouncement: '我知道了'/)
  assert.match(i18n, /majorAnnouncement: 'Major Announcement'/)
  assert.match(i18n, /acknowledgeMajorAnnouncement: 'Got it'/)
})

test('notification center lets the account mark viewed and delete its own message', () => {
  const api = read('../src/api/notification.ts')
  const page = read('../src/pages/notifications/index.vue')
  const i18n = read('../src/store/i18n.ts')

  assert.match(api, /deleteNotification\(id: number\)/)
  assert.match(api, /method: 'DELETE'/)
  assert.match(page, /onMarkViewed\(notification\)/)
  assert.match(page, /onDelete\(notification\)/)
  assert.match(page, /deleteNotification\(notification\.id\)/)
  assert.match(i18n, /markViewed: '标为已查看'/)
  assert.match(i18n, /deleteNotificationConfirm:/)
})
