<template>
  <view class="page">
    <AppNavBar :title="t('k_4a830cdb')" />
    <view v-if="loading" class="detail-state">{{ t('loading') }}</view>
    <view v-else-if="loadError" class="detail-state detail-error">
      <text>{{ t('dataUnavailable') }}</text>
      <view class="retry-button" role="button" @tap="loadDetail">{{ t('retry') }}</view>
    </view>
    <view class="shell" v-else-if="post">
      <view class="card dcard">
        <view class="dhead">
          <view class="davatar">{{ authorInitial(post.author_name) }}</view>
          <view class="dinfo">
            <text class="dname">{{ authorName(post.author_name) }}</text>
            <text class="dtime">{{ formatDate(post.source_published_at || post.created_at) }} · {{ postTopic(post) }}</text>
          </view>
          <view v-if="!post.is_own" class="fbtn" :class="{ following: post.is_following }" @tap="onFollow">
            <text>{{ t(post.is_following ? '已关注' : '+ 关注') }}</text>
          </view>
        </view>
        <view v-if="isAutoPost(post)" class="source-meta">
          <text class="auto-badge">{{ t('autoNews') }}</text>
          <text class="source-name">{{ displaySource(post) }}</text>
        </view>
        <text class="dtext">{{ postContent(post) }}</text>
        <view v-if="postImages(post).length" class="post-images" :class="{ single: postImages(post).length === 1 }">
          <image
            v-for="(imageUrl, imageIndex) in postImages(post)"
            :key="imageUrl"
            class="post-image"
            :src="imageUrl"
            mode="aspectFill"
            @tap="previewPostImages(post, imageIndex)"
          />
        </view>
        <video
          v-if="userVideoUrl(post)"
          class="user-video"
          :src="userVideoUrl(post)"
          controls
          :show-center-play-btn="true"
          :enable-progress-gesture="true"
        />
        <view v-else-if="post.content_type === 'video'" class="dvideo">
          <!-- #ifdef H5 -->
          <iframe
            v-if="playerUrl(post)"
            class="video-frame"
            :src="playerUrl(post)"
            title="Video player"
            frameborder="0"
            allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            referrerpolicy="strict-origin-when-cross-origin"
            allowfullscreen
          />
          <!-- #endif -->
          <!-- #ifndef H5 -->
          <view class="vthumb" @tap="openVideo(post)">
            <image v-if="post.thumbnail_url" class="vimage" :src="post.thumbnail_url" mode="aspectFill" />
            <view class="vshade" />
            <view class="vplay">▶</view>
          </view>
          <!-- #endif -->
          <view v-if="!hasInAppVideo(post)" class="video-unavailable">{{ t('videoUnavailable') }}</view>
        </view>
        <view v-if="post.source_url && post.content_type !== 'video'" class="source-action" @tap="openSource(post)">
          <view>
            <text class="source-caption">{{ t('sourceLabel') }}</text>
            <text class="source-value">{{ displaySource(post) }}</text>
          </view>
          <text class="source-link">{{ t('viewOriginal') }} ↗</text>
        </view>
        <view class="dactions">
          <view class="dact" @tap="onLike">
            <text class="like-icon" :class="{ liked: post.is_liked }">{{ post.is_liked ? '♥' : '♡' }}</text>
            <text class="like-text" :class="{ liked: post.is_liked }">{{ post.likes }}</text>
          </view>
          <view class="dact">
            <AppIcon name="comment" :size="32" />
            <text>{{ post.comments }}</text>
          </view>
          <view class="dact" @tap="onShare">
            <AppIcon name="share" :size="32" />
            <text>{{ t("share") }}</text>
          </view>
        </view>
      </view>
      <SectionHeader :title="t('k_55374d7b')" />
      <view v-if="commentsError" class="comment-error">
        <text>{{ t('dataUnavailable') }}</text>
        <text class="comment-retry" role="button" @tap="loadComments">{{ t('retry') }}</text>
      </view>
      <view v-else-if="!comments.length" class="card ph"><EmptyState text="暂无评论，快来抢沙发" /></view>
      <view v-for="c in comments" :key="c.id" class="card cmt">
        <view class="cavatar">{{ authorInitial(c.author_name) }}</view>
        <view class="cbody">
          <text class="cname">{{ authorName(c.author_name) }}</text>
          <text class="ctext">{{ communityText(c.content) }}</text>
          <text class="ctime">{{ formatDate(c.created_at) }}</text>
        </view>
      </view>
      <view class="bottom-spacer" />
    </view>
    <view v-if="post" class="input-bar" :style="{ paddingBottom: 'calc(16rpx + var(--safe-bottom))' }">
      <input class="cinput" v-model="commentText" :placeholder="t('k_f3863e13')" placeholder-class="cph" :adjust-position="true" @confirm="onComment" />
      <view class="csend" @tap="onComment">{{ t('k_1535fcfa') }}</view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getPostDetail, getComments, createComment, toggleLike, toggleFollow, type PostItem, type CommentItem } from '@/api/community'
import { formatDate } from '@/utils/format'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import AppIcon from '@/components/AppIcon.vue'
import { useI18nStore } from '@/store/i18n'
import { localizeCommunityText, localizeInternalBrandText, localizePersonName } from '@/utils/localize-content'
import { openExternalLink } from '@/utils/external-link'
import { buildCommunityVideoPlayerUrl, buildCommunityVideoSourceUrl, openCommunityVideo } from '@/utils/community-video'
import { resolveApiMediaUrl } from '@/utils/config'

const i18n = useI18nStore()
const { t } = i18n
const post = ref<PostItem | null>(null)
const comments = ref<CommentItem[]>([])
const commentText = ref('')
const loading = ref(true)
const loadError = ref(false)
const commentsError = ref(false)
const pid = ref(0)

function authorName(value?: string): string {
  return localizePersonName(value || t('匿名'), i18n.lang)
}

function authorInitial(value?: string): string {
  return authorName(value || 'W').slice(0, 1).toUpperCase()
}

function communityText(value?: string): string {
  return localizeCommunityText(value || '', i18n.lang)
}

function postContent(value: PostItem): string {
  const content = i18n.lang === 'en' && value.content_en ? value.content_en : communityText(value.content)
  return localizeInternalBrandText(content, value.source_key)
}

function postTopic(value: PostItem): string {
  const topic = i18n.lang === 'en' && value.topic_en ? value.topic_en : communityText(value.topic || t('讨论'))
  return localizeInternalBrandText(topic, value.source_key)
}

function isAutoPost(value: PostItem): boolean {
  return value.origin === 'aggregated' || value.origin === 'internal'
}

function displaySource(value: PostItem): string {
  if (value.source_key === 'wod-market') return t('ztwMarketName')
  return value.source_name ? i18n.tr(value.source_name) : t('sourceLabel')
}

function openSource(value: PostItem) {
  const url = value.source_url || value.video_url
  if (!url) return
  openExternalLink(url, () => uni.showToast({ title: t('openFailed'), icon: 'none' }))
}

function watchVideo(value: PostItem): boolean {
  if (!buildCommunityVideoPlayerUrl(value)) return false
  let failed = false
  const opened = openCommunityVideo(value, t('video'), () => {
    failed = true
    const url = buildCommunityVideoSourceUrl(value)
    if (!url) {
      uni.showToast({ title: t('videoUnavailable'), icon: 'none' })
      return
    }
    uni.showModal({
      title: t('videoUnavailable'),
      content: t('videoOpenExternalHint'),
      confirmText: t('confirm'),
      cancelText: t('cancel'),
      success: ({ confirm }) => {
        if (confirm) openExternalLink(url, () => uni.showToast({ title: t('openFailed'), icon: 'none' }))
      },
    })
  })
  return opened || failed
}

function openVideo(value: PostItem) {
  if (!watchVideo(value)) uni.showToast({ title: t('videoUnavailable'), icon: 'none' })
}

function postImages(value: PostItem): string[] {
  if (value.origin !== 'user' || !Array.isArray(value.images)) return []
  return value.images.map(resolveApiMediaUrl).filter(Boolean)
}

function userVideoUrl(value: PostItem): string {
  return value.origin === 'user' ? resolveApiMediaUrl(value.video) : ''
}

function previewPostImages(value: PostItem, currentIndex: number) {
  const urls = postImages(value)
  if (!urls.length) return
  uni.previewImage({ current: urls[currentIndex], urls })
}

function hasInAppVideo(value: PostItem): boolean {
  return Boolean(userVideoUrl(value) || buildCommunityVideoPlayerUrl(value))
}

function playerUrl(value: PostItem): string {
  return buildCommunityVideoPlayerUrl(value)
}

onLoad((opts) => {
  pid.value = Number(opts?.id || 0)
  void loadDetail()
})

async function loadDetail() {
  loading.value = true
  loadError.value = false
  commentsError.value = false
  if (!pid.value) {
    loadError.value = true
    loading.value = false
    return
  }
  const [postResult, commentsResult] = await Promise.allSettled([
    getPostDetail(pid.value),
    getComments(pid.value),
  ])
  if (postResult.status === 'rejected') {
    loadError.value = true
    post.value = null
  } else {
    post.value = postResult.value
  }
  if (commentsResult.status === 'fulfilled') comments.value = commentsResult.value
  else commentsError.value = true
  loading.value = false
}

async function loadComments() {
  if (!pid.value) return
  commentsError.value = false
  try { comments.value = await getComments(pid.value) }
  catch { commentsError.value = true }
}

async function onLike() {
  if (!post.value) return
  try {
    const res = await toggleLike(pid.value)
    post.value.is_liked = res.liked
    post.value.likes = res.likes
  } catch {}
}

async function onFollow() {
  if (!post.value) return
  try {
    const res = await toggleFollow(post.value.user_id)
    post.value.is_following = res.following
  } catch {}
}

function onShare() {
  if (!post.value) return
  uni.setClipboardData({
    data: `${postContent(post.value).slice(0, 100)}${post.value.source_url ? `\n${post.value.source_url}` : ''}`,
    success: () => uni.showToast({ title: t('copied'), icon: 'success' }),
  })
}

async function onComment() {
  if (!commentText.value.trim()) return
  try {
    const c = await createComment(pid.value, commentText.value)
    comments.value.unshift(c)
    commentText.value = ''
    if (post.value) post.value.comments++
    uni.showToast({ title: t('commentSuccess'), icon: 'success' })
  } catch {}
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.detail-state { min-height: 420rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 26rpx; }
.detail-error { flex-direction: column; gap: 18rpx; }
.retry-button { min-height: 68rpx; padding: 0 28rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: var(--radius); font-weight: 700; }
.comment-error { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 22rpx 24rpx; margin-bottom: 20rpx; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 23rpx; }
.comment-retry { min-height: 64rpx; flex-shrink: 0; display: flex; align-items: center; color: var(--primary); font-weight: 700; }
.shell { padding: 0 32rpx calc(124rpx + var(--safe-bottom)); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); }
.dcard { padding: 32rpx; margin-bottom: 24rpx; }
.dhead { display: flex; align-items: center; margin-bottom: 20rpx; }
.davatar { width: 72rpx; height: 72rpx; border-radius: 36rpx; background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; font-size: 32rpx; font-weight: 700; display: flex; align-items: center; justify-content: center; margin-right: 20rpx; }
.dinfo { flex: 1; }
.dname { color: var(--text); font-size: 28rpx; font-weight: 600; display: block; }
.dtime { color: var(--text-dim); font-size: 22rpx; display: block; margin-top: 4rpx; }
.fbtn { padding: 8rpx 24rpx; border-radius: 32rpx; background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; font-size: 22rpx; font-weight: 600; flex-shrink: 0; }
.fbtn.following { background: var(--bg); color: var(--text-sub); border: 1rpx solid var(--border); }
.dtext { color: var(--text); font-size: 28rpx; line-height: 1.6; display: block; margin-bottom: 20rpx; }
.post-images { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8rpx; margin-bottom: 20rpx; }
.post-images.single { grid-template-columns: 1fr; }
.post-image { width: 100%; height: 210rpx; border-radius: 12rpx; background: var(--bg); }
.post-images.single .post-image { height: 480rpx; }
.user-video { display: block; width: 100%; height: 440rpx; margin-bottom: 20rpx; border-radius: var(--radius); background: #111827; overflow: hidden; }
.source-meta { display: flex; align-items: center; gap: 12rpx; margin: -2rpx 0 16rpx; min-width: 0; }
.auto-badge { flex-shrink: 0; padding: 4rpx 12rpx; border-radius: 8rpx; background: rgba(24,175,196,0.12); color: var(--primary); font-size: 20rpx; font-weight: 600; }
.source-name { color: var(--text-sub); font-size: 22rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dvideo { margin-bottom: 20rpx; }
.video-frame { display: block; width: 100%; height: 420rpx; min-height: 200px; border: 0; border-radius: var(--radius); background: #111827; }
.vthumb { height: 360rpx; border-radius: var(--radius); background: linear-gradient(135deg, #1A1F29, #2A2F3A); overflow: hidden; display: flex; align-items: center; justify-content: center; position: relative; }
.vimage { position: absolute; inset: 0; width: 100%; height: 100%; }
.vshade { position: absolute; inset: 0; background: rgba(12,17,25,0.2); }
.vplay { position: relative; z-index: 2; width: 88rpx; height: 88rpx; border-radius: 50%; background: rgba(255,255,255,0.94); color: #111827; display: flex; align-items: center; justify-content: center; padding-left: 5rpx; font-size: 34rpx; }
.video-unavailable { min-height: 240rpx; border-radius: var(--radius); background: #1A1F29; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 24rpx; }
.source-action { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; margin-bottom: 20rpx; padding: 18rpx 20rpx; border-radius: 12rpx; background: var(--bg); }
.source-caption { display: block; color: var(--text-dim); font-size: 20rpx; }
.source-value { display: block; color: var(--text-sub); font-size: 23rpx; margin-top: 3rpx; }
.source-link { flex-shrink: 0; color: var(--primary); font-size: 23rpx; font-weight: 600; }
.dactions { display: flex; gap: 48rpx; padding-top: 16rpx; border-top: 1rpx solid var(--divider); }
.dact { display: flex; align-items: center; gap: 8rpx; color: var(--text-sub); font-size: 24rpx; }
.like-icon { font-size: 32rpx; color: var(--text-sub); }
.like-icon.liked { color: var(--down); }
.like-text { color: var(--text-sub); }
.like-text.liked { color: var(--down); }
.ph { padding: 60rpx 0; }
.cmt { display: flex; padding: 28rpx; margin-bottom: 16rpx; }
.cavatar { width: 64rpx; height: 64rpx; border-radius: 32rpx; background: var(--bg-2); color: var(--primary); font-size: 28rpx; font-weight: 700; display: flex; align-items: center; justify-content: center; margin-right: 20rpx; flex-shrink: 0; }
.cbody { flex: 1; }
.cname { color: var(--text); font-size: 26rpx; font-weight: 600; display: block; }
.ctext { color: var(--text); font-size: 26rpx; margin-top: 8rpx; display: block; line-height: 1.5; }
.ctime { color: var(--text-dim); font-size: 20rpx; margin-top: 8rpx; display: block; }
.bottom-spacer { height: calc(120rpx + var(--safe-bottom)); }
.input-bar { position: fixed; left: 0; right: 0; bottom: 0; z-index: 100; display: flex; gap: 16rpx; padding: 16rpx 32rpx calc(16rpx + var(--safe-bottom)); background: var(--card); border-top: 1rpx solid var(--border); box-shadow: 0 -4rpx 16rpx var(--shadow); }
.cinput { flex: 1; height: 72rpx; line-height: 72rpx; background: var(--bg); border-radius: var(--radius); padding: 0 24rpx; color: var(--text); font-size: 28rpx; }
.cph { color: var(--text-dim); }
.csend { background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; padding: 20rpx 36rpx; border-radius: var(--radius); font-size: 28rpx; font-weight: 600; }
</style>
