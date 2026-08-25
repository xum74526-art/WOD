import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

import { HOME_NOTICES, HOME_PROMOTIONS } from '../src/config/home-promotions.ts'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const homePage = source('../src/pages/index/index.vue')
const carousel = source('../src/components/HomePromoCarousel.vue')
const appStyles = source('../src/App.vue')
const i18n = source('../src/store/i18n.ts')
const pages = JSON.parse(source('../src/pages.json')) as {
  tabBar: { list: Array<{ pagePath: string; text: string }> }
}
const zhLocale = JSON.parse(source('../src/locale/zh-Hans.json')) as Record<string, string>
const enLocale = JSON.parse(source('../src/locale/en.json')) as Record<string, string>

test('homepage app promotions use the approved local assets and real internal routes', () => {
  assert.deepEqual(HOME_PROMOTIONS.map((item) => item.route), [
    '/pages/market/index',
    '/pages/quote/index',
    '/pages/wallet/index',
  ])
  assert.deepEqual(HOME_PROMOTIONS.map((item) => item.image), [
    '/static/gpu/RTX5090.jpg',
    '/static/gpu/H100.jpg',
    '/static/gpu/RTX4090.jpg',
  ])
  assert.equal(HOME_PROMOTIONS[0]?.id, 'hourly')
  for (const item of HOME_PROMOTIONS) {
    assert.equal(item.image.startsWith('/static/'), true)
    assert.equal(existsSync(new URL(`../src${item.image}`, import.meta.url)), true, `${item.image} must be bundled`)
  }
  assert.deepEqual(HOME_NOTICES.map((item) => item.route), HOME_PROMOTIONS.map((item) => item.route))
})

test('promotion carousel uses a dark media card with internal paging and no playback control', () => {
  const heroPosition = homePage.indexOf('<view class="hero">')
  const carouselPosition = homePage.indexOf('<HomePromoCarousel />')
  const firstDividerPosition = homePage.indexOf('<view class="divider"></view>')
  assert.ok(heroPosition >= 0 && carouselPosition > heroPosition && carouselPosition < firstDividerPosition)
  assert.match(homePage, /import HomePromoCarousel from '@\/components\/HomePromoCarousel\.vue'/)
  assert.match(carousel, /:autoplay="autoplayEnabled"/)
  assert.match(carousel, /circular/)
  assert.match(carousel, /class="promo-stage"/)
  assert.match(carousel, /class="promo-inline-controls"/)
  assert.match(carousel, /class="promo-background"[\s\S]*?mode="aspectFill"/)
  assert.match(carousel, /class="promo-shade"/)
  assert.match(carousel, /background: #081A20;/)
  assert.match(carousel, /background: #8EDDE7;/)
  assert.match(carousel, /@tap\.stop="previousSlide"/)
  assert.match(carousel, /@tap\.stop="nextSlide"/)
  assert.match(carousel, /function previousSlide\(\)/)
  assert.match(carousel, /function nextSlide\(\)/)
  assert.doesNotMatch(carousel, /promo-motion-toggle|togglePaused|motion-icon--play|motion-icon--pause/)
  assert.doesNotMatch(carousel, /homeCarouselPause|homeCarouselResume/)
  assert.match(carousel, /class="notice-swiper"[\s\S]*?vertical/)
})

test('homepage uses a light cool card surface without changing other pages', () => {
  assert.match(appStyles, /--home-card: #F6F8F8;/)
  assert.match(appStyles, /--home-card: rgba\(255, 255, 255, 0\.07\);/)
  assert.match(homePage, /--card: var\(--home-card\);/)
  assert.match(homePage, /--card-border: var\(--home-card-border\);/)
})

test('all pre-existing live homepage sections remain wired to their original components and APIs', () => {
  for (const marker of [
    'class="topbar"',
    'class="price-bar"',
    'class="quick"',
    "t('runningCompute')",
    "t('hotComputeTrends')",
    '<CandlestickChart',
    "t('revenueTrend')",
    '<Chart :points="chart"',
    "t('featuredCompute')",
    'v-for="p in hot"',
    'getMarketRanking(silent)',
    'getMarketCandles(',
    'getRevenueChart(7)',
    "getProducts({ page_size: 100, market_source: 'kai', representative: true })",
  ]) assert.ok(homePage.includes(marker), `homepage must retain ${marker}`)
})

test('community remains the internal route while its visible tab name is News', () => {
  const communityTab = pages.tabBar.list.find((item) => item.pagePath === 'pages/community/index')
  assert.equal(communityTab?.text, '资讯')
  assert.equal(zhLocale['tab.community'], '资讯')
  assert.equal(enLocale['tab.community'], 'News')
  assert.match(i18n, /tabCommunity: '资讯'/)
  assert.match(i18n, /tabCommunity: 'News'/)
  assert.match(homePage + carousel, /pages\/(?:quote|market|wallet)\/index/)
  assert.equal(pages.tabBar.list.some((item) => item.pagePath === 'pages/community/index'), true)
})
