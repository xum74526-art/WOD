<template>
  <view :class="['page', pageMotionClass]">
    <view class="shell" :style="{ paddingTop: 'calc(28rpx + var(--safe-top))' }">
      <!-- 搜索栏 -->
      <view v-if="searching" class="search-bar">
        <view class="s-input-wrap">
          <AppIcon name="search" :size="32" />
          <input class="s-input" v-model="keyword" :placeholder="t('k_80c2deec')" placeholder-class="s-ph" :focus="true" @input="onSearchInput" />
          <view v-if="keyword" class="s-clear" @tap="clearKeyword"><AppIcon name="minus" :size="28" /></view>
        </view>
        <text class="s-cancel" @tap="exitSearch">{{ t("cancel") }}</text>
      </view>
      <!-- 正常模式 topbar -->
      <view v-else class="topbar">
        <text class="title">{{ t("tabCommunity") }}</text>
        <view class="top-actions" @tap="enterSearch"><AppIcon name="search" :size="40" /></view>
      </view>
      <view v-if="!searching" class="seg-wrap"><SegmentedControl :items="[t('recommend'), t('follow'), t('latest')]" :model-value="tab" @update:model-value="onTab" /></view>

      <view v-if="loading && !list.length" class="state">{{ t("loading") }}</view>
      <view v-else-if="loadError && !list.length" class="state error-state">
        <text>{{ t('dataUnavailable') }}</text>
        <view class="retry-button" role="button" @tap="load(true)">{{ t('retry') }}</view>
      </view>
      <view v-else-if="!list.length" class="card ph">
        <EmptyState :text="searching ? t('noResults') : t('noPosts')" />
      </view>
      <view v-for="d in list" :key="d.id" class="card dcard" @tap="goDetail(d.id)">
        <view class="dhead">
          <view class="davatar">{{ authorInitial(d.author_name) }}</view>
          <view class="dinfo">
            <text class="dname">{{ authorName(d.author_name) }}</text>
            <text class="dtime">{{ formatDate(d.source_published_at || d.created_at) }} · {{ postTopic(d) }}</text>
          </view>
          <view v-if="!d.is_own" class="fbtn" :class="{ following: d.is_following }" @tap.stop="onFollow(d)">
            <text>{{ t(d.is_following ? '已关注' : '+ 关注') }}</text>
          </view>
        </view>
        <view v-if="isAutoPost(d)" class="source-meta">
          <text class="auto-badge">{{ t('autoNews') }}</text>
          <text class="source-name">{{ displaySource(d) }}</text>
        </view>
        <text class="dtext">{{ postContent(d) }}</text>
        <view v-if="postImages(d).length" class="post-images" :class="{ single: postImages(d).length === 1 }">
          <image
            v-for="(imageUrl, imageIndex) in postImages(d)"
            :key="imageUrl"
            class="post-image"
            :src="imageUrl"
            mode="aspectFill"
            @tap.stop="previewPostImages(d, imageIndex)"
          />
        </view>
        <video
          v-if="userVideoUrl(d)"
          class="user-video"
          :src="userVideoUrl(d)"
          controls
          :show-center-play-btn="true"
          :enable-progress-gesture="true"
          @tap.stop
        />
        <view v-else-if="d.content_type === 'video'" class="dvideo" @tap.stop="goDetail(d.id)">
          <view class="vthumb">
            <image v-if="d.thumbnail_url" class="vimage" :src="d.thumbnail_url" mode="aspectFill" />
            <view class="vshade" />
            <view class="vplay">▶</view>
            <text class="vlabel">{{ t('officialVideo') }}</text>
          </view>
        </view>
        <view v-if="d.source_url && d.content_type !== 'video'" class="source-action" @tap.stop="openSource(d)">
          <text>{{ t('viewOriginal') }}</text>
          <text>↗</text>
        </view>
        <view class="dactions">
          <view class="dact" @tap.stop="onLike(d)">
            <text class="like-icon" :class="{ liked: d.is_liked }">{{ d.is_liked ? '♥' : '♡' }}</text>
            <text class="like-text" :class="{ liked: d.is_liked }">{{ d.likes }}</text>
          </view>
          <view class="dact" @tap.stop="goDetail(d.id)">
            <AppIcon name="comment" :size="32" />
            <text>{{ d.comments }}</text>
          </view>
          <view class="dact" @tap.stop="onShare(d)">
            <AppIcon name="share" :size="32" />
            <text>{{ t("share") }}</text>
          </view>
        </view>
      </view>
      <view v-if="loading && list.length" class="state">{{ t('loadMore') }}</view>
      <view v-if="finished && list.length" class="state">{{ t("noMore") }}</view>
    </view>
    <view class="fab pressable" @tap="goPublish"><AppIcon name="plus" :size="44" color="#fff" /></view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow, onReachBottom } from '@dcloudio/uni-app'
import { getPosts, setFollow, setLike, type PostItem } from '@/api/community'
import { formatDate } from '@/utils/format'
import { navigateTo as nav } from '@/utils/nav'
import { openExternalLink } from '@/utils/external-link'
import AppIcon from '@/components/AppIcon.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useI18nStore } from '@/store/i18n'
import { localizeCommunityText, localizeInternalBrandText, localizePersonName } from '@/utils/localize-content'
import { resolveApiMediaUrl } from '@/utils/config'
import { usePageMotion } from '@/utils/page-motion'

const i18n = useI18nStore()
const { t } = i18n
const { pageMotionClass } = usePageMotion()
const list = ref<PostItem[]>([])
const loading = ref(false)
const loadError = ref(false)
const finished = ref(false)
const page = ref(1)
const tab = ref(0)
const TAB_MAP = ['recommend', 'follow', 'latest']

function authorName(value?: string): string {
  return localizePersonName(value || t('匿名'), i18n.lang)
}

function authorInitial(value?: string): string {
  return authorName(value || 'W').slice(0, 1).toUpperCase()
}

function communityText(value?: string): string {
  return localizeCommunityText(value || '', i18n.lang)
}

function postContent(post: PostItem): string {
  const content = i18n.lang === 'en' && post.content_en ? post.content_en : communityText(post.content)
  return localizeInternalBrandText(content, post.source_key)
}

function postTopic(post: PostItem): string {
  const topic = i18n.lang === 'en' && post.topic_en ? post.topic_en : communityText(post.topic || t('讨论'))
  return localizeInternalBrandText(topic, post.source_key)
}

function isAutoPost(post: PostItem): boolean {
  return post.origin === 'aggregated' || post.origin === 'internal'
}

function displaySource(post: PostItem): string {
  if (post.source_key === 'wod-market') return t('ztwMarketName')
  return post.source_name ? i18n.tr(post.source_name) : t('sourceLabel')
}

function openSource(post: PostItem) {
  const url = post.source_url || post.video_url
  if (!url) return
  openExternalLink(url, () => uni.showToast({ title: t('openFailed'), icon: 'none' }))
}

function postImages(post: PostItem): string[] {
  if (post.origin !== 'user' || !Array.isArray(post.images)) return []
  return post.images.map(resolveApiMediaUrl).filter(Boolean)
}

function userVideoUrl(post: PostItem): string {
  return post.origin === 'user' ? resolveApiMediaUrl(post.video) : ''
}

function previewPostImages(post: PostItem, currentIndex: number) {
  const urls = postImages(post)
  if (!urls.length) return
  uni.previewImage({ current: urls[currentIndex], urls })
}

const searching = ref(false)
const keyword = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null
let loadGeneration = 0
const likeInFlight = new Set<number>()
const followInFlight = new Set<number>()

async function load(reset = false) {
  if (!reset && loading.value) return
  if (reset) {
    loadGeneration++
    page.value = 1
    list.value = []
    finished.value = false
    loadError.value = false
  }
  if (finished.value) return
  const generation = loadGeneration
  const requestedPage = page.value
  loading.value = true
  try {
    const res = await getPosts(TAB_MAP[tab.value], requestedPage, keyword.value)
    if (generation !== loadGeneration) return
    const seen = new Set(list.value.map((item) => item.id))
    list.value.push(...res.items.filter((item) => !seen.has(item.id) && seen.add(item.id)))
    if (list.value.length >= res.total) finished.value = true
    else page.value = requestedPage + 1
  } catch {
    if (generation === loadGeneration && requestedPage === 1) loadError.value = true
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}
onShow(() => { i18n.updateTabBar(); load(true) })
onReachBottom(() => load())
function onTab(v: number) { tab.value = v; load(true) }

function enterSearch() {
  searching.value = true
  keyword.value = ''
  list.value = []
  finished.value = true
}

function exitSearch() {
  searching.value = false
  keyword.value = ''
  load(true)
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (!keyword.value.trim()) {
      list.value = []
      finished.value = true
      return
    }
    load(true)
  }, 400)
}

function clearKeyword() {
  keyword.value = ''
  list.value = []
  finished.value = true
}

async function onLike(d: PostItem) {
  if (likeInFlight.has(d.id)) return
  const targetLiked = !d.is_liked
  likeInFlight.add(d.id)
  try {
    const res = await setLike(d.id, targetLiked)
    const current = list.value.find(item => item.id === d.id)
    if (!current) return
    current.is_liked = res.liked
    current.likes = res.likes
  } catch {}
  finally { likeInFlight.delete(d.id) }
}

function onShare(d: PostItem) {
  uni.setClipboardData({
    data: `${postContent(d).slice(0, 100)}${d.source_url ? `\n${d.source_url}` : ''}`,
    success: () => uni.showToast({ title: t('copied'), icon: 'success' }),
  })
}

async function onFollow(d: PostItem) {
  if (followInFlight.has(d.user_id)) return
  const targetFollowing = !d.is_following
  followInFlight.add(d.user_id)
  try {
    const res = await setFollow(d.user_id, targetFollowing)
    list.value.forEach(p => {
      if (p.user_id === d.user_id) p.is_following = res.following
    })
  } catch {}
  finally { followInFlight.delete(d.user_id) }
}

function goPublish() { nav('/pages/community/publish') }
function goDetail(id: number) { nav('/pages/community/detail?id=' + id) }
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.topbar { min-height: 88rpx; display: flex; justify-content: space-between; align-items: center; padding: 8rpx 0 16rpx; }
.title { color: var(--text); font-size: 44rpx; font-weight: 700; }
.top-actions { width: 88rpx; height: 88rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); }
.search-bar { display: flex; align-items: center; gap: 20rpx; padding: 8rpx 0 20rpx; }
.s-input-wrap { flex: 1; display: flex; align-items: center; gap: 12rpx; height: 72rpx; background: var(--card); border-radius: 36rpx; padding: 0 24rpx; border: 1rpx solid var(--border); }
.s-input { flex: 1; height: 72rpx; line-height: 72rpx; font-size: 28rpx; color: var(--text); }
.s-ph { color: var(--text-dim); }
.s-clear { width: 40rpx; height: 40rpx; display: flex; align-items: center; justify-content: center; }
.s-cancel { min-height: 88rpx; display: flex; align-items: center; color: var(--primary); font-size: 28rpx; font-weight: 600; flex-shrink: 0; }
.seg-wrap { margin: 16rpx 0 24rpx; }
.state { color: var(--text-sub); text-align: center; padding: 40rpx 0; font-size: 26rpx; }
.error-state { display: flex; flex-direction: column; align-items: center; gap: 18rpx; }
.retry-button { min-height: 68rpx; padding: 0 28rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: var(--radius); font-weight: 700; }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); box-shadow: 0 4rpx 24rpx var(--card-border); }
.ph { padding: 60rpx 0; }
.dcard { padding: 32rpx; margin-bottom: 20rpx; }
.dhead { display: flex; align-items: center; margin-bottom: 20rpx; }
.davatar { width: 72rpx; height: 72rpx; border-radius: 36rpx; background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; font-size: 32rpx; font-weight: 700; display: flex; align-items: center; justify-content: center; margin-right: 20rpx; }
.dinfo { flex: 1; }
.dname { color: var(--text); font-size: 28rpx; font-weight: 600; display: block; }
.dtime { color: var(--text-dim); font-size: 22rpx; display: block; margin-top: 4rpx; }
.fbtn { min-height: 72rpx; display: flex; align-items: center; padding: 8rpx 24rpx; border-radius: 36rpx; background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; font-size: 22rpx; font-weight: 600; flex-shrink: 0; }
.fbtn.following { background: var(--bg); color: var(--text-sub); border: 1rpx solid var(--border); }
.dtext { color: var(--text); font-size: 28rpx; line-height: 1.6; display: block; margin-bottom: 20rpx; }
.post-images { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8rpx; margin-bottom: 20rpx; }
.post-images.single { grid-template-columns: 1fr; }
.post-image { width: 100%; height: 200rpx; border-radius: 12rpx; background: var(--bg); }
.post-images.single .post-image { height: 420rpx; }
.user-video { display: block; width: 100%; height: 380rpx; margin-bottom: 20rpx; border-radius: var(--radius); background: #111827; overflow: hidden; }
.source-meta { display: flex; align-items: center; gap: 12rpx; margin: -2rpx 0 16rpx; min-width: 0; }
.auto-badge { flex-shrink: 0; padding: 4rpx 12rpx; border-radius: 8rpx; background: rgba(24,175,196,0.12); color: var(--primary); font-size: 20rpx; font-weight: 600; }
.source-name { color: var(--text-sub); font-size: 22rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dvideo { margin-bottom: 20rpx; }
.vthumb { height: 360rpx; border-radius: var(--radius); background: linear-gradient(135deg, #1A1F29, #2A2F3A); overflow: hidden; display: flex; align-items: center; justify-content: center; position: relative; }
.vimage { position: absolute; inset: 0; width: 100%; height: 100%; }
.vshade { position: absolute; inset: 0; background: rgba(12,17,25,0.2); }
.vplay { position: relative; z-index: 2; width: 88rpx; height: 88rpx; border-radius: 50%; background: rgba(255,255,255,0.94); color: #111827; display: flex; align-items: center; justify-content: center; padding-left: 5rpx; font-size: 34rpx; box-shadow: 0 8rpx 24rpx rgba(0,0,0,0.2); }
.vlabel { position: absolute; z-index: 2; left: 20rpx; bottom: 18rpx; color: #fff; font-size: 22rpx; background: rgba(0,0,0,0.62); padding: 5rpx 12rpx; border-radius: 8rpx; }
.source-action { display: flex; align-items: center; justify-content: space-between; margin: -2rpx 0 18rpx; padding: 16rpx 20rpx; border-radius: 12rpx; background: var(--bg); color: var(--primary); font-size: 24rpx; font-weight: 600; }
.dactions { display: flex; gap: 48rpx; padding-top: 16rpx; border-top: 1rpx solid var(--divider); }
.dact { min-height: 64rpx; display: flex; align-items: center; gap: 8rpx; color: var(--text-sub); font-size: 24rpx; }
.like-icon { font-size: 32rpx; color: var(--text-sub); }
.like-icon.liked { color: var(--down); }
.like-text { color: var(--text-sub); }
.like-text.liked { color: var(--down); }
.fab { position: fixed; right: 32rpx; bottom: calc(160rpx + var(--safe-bottom)); width: 96rpx; height: 96rpx; border-radius: 48rpx; background: linear-gradient(135deg, var(--primary), var(--primary)); display: flex; align-items: center; justify-content: center; box-shadow: 0 8rpx 32rpx rgba(24,175,196,0.3); z-index: 90; }
</style>
