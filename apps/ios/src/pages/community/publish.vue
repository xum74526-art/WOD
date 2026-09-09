<template>
  <view class="page">
    <AppNavBar :title="t('publish')" />
    <view class="shell">
      <view class="type-row">
        <view class="type-i" :class="{ active: type === 'text' }" @tap="switchType('text')">✍️ {{ t('文字') }}</view>
        <view class="type-i" :class="{ active: type === 'image' }" @tap="switchType('image')">📷 {{ t('图文') }}</view>
        <view class="type-i" :class="{ active: type === 'video' }" @tap="switchType('video')">🎬 {{ t('视频') }}</view>
      </view>
      <view class="card form">
        <textarea class="tarea" v-model="form.content" :placeholder="t('k_a5248a2b')" placeholder-class="ph" maxlength="500" />
        <view v-if="type === 'image' && imageDrafts.length" class="image-grid">
          <view v-for="item in imageDrafts" :key="item.id" class="image-cell" @tap="previewImage(item.localPath)">
            <image class="image-preview" :src="item.localPath" mode="aspectFill" />
            <view class="remove-media" :class="{ disabled: isMediaBusy(item.status) }" @tap.stop="removeImage(item)">×</view>
            <view v-if="item.status !== 'ready'" class="media-state" @tap.stop="item.status === 'failed' && uploadImage(item)">
              <text>{{ mediaStatusText(item) }}</text>
              <view v-if="isMediaBusy(item.status)" class="media-progress"><view :style="{ width: `${item.progress}%` }" /></view>
            </view>
          </view>
        </view>
        <view v-if="type === 'video' && videoDraft" class="video-preview-wrap">
          <video class="video-preview" :src="videoDraft.localPath" controls :show-center-play-btn="true" />
          <view class="video-meta">
            <text>{{ t('videoDuration') }} {{ formatDuration(videoDraft.duration) }}</text>
            <text v-if="isMediaBusy(videoDraft.status)" class="uploading-text">{{ mediaStatusText(videoDraft) }}</text>
            <text v-else-if="videoDraft.status === 'failed'" class="failed-text" @tap="uploadVideo(videoDraft)">{{ t('retryUpload') }}</text>
            <text v-else class="ready-text">{{ t('mediaUploadReady') }}</text>
            <text class="remove-text" :class="{ disabled: isMediaBusy(videoDraft.status) }" @tap="removeVideo">{{ t('removeMedia') }}</text>
          </view>
          <view v-if="isMediaBusy(videoDraft.status)" class="video-progress"><view :style="{ width: `${videoDraft.progress}%` }" /></view>
        </view>
        <view v-if="type !== 'text' && (type === 'video' ? !videoDraft : imageDrafts.length < 9)" class="media-pick" @tap="pickMedia">
          <AppIcon name="plus" :size="48" />
          <text class="mp-text">{{ t('添加') }}{{ t(type === 'video' ? '视频' : '图片') }}</text>
          <text class="media-limit">{{ t(type === 'video' ? 'videoUploadLimit' : 'imageUploadLimit') }}</text>
        </view>
        <view class="topic-row">
          <text class="topic-t"># {{ t('话题') }}</text>
          <input class="topic-i" v-model="form.topic" :placeholder="t('k_af4399f5')" placeholder-class="ph" />
        </view>
      </view>
      <view class="btn-primary" :class="{ disabled: submitting || hasUploadingMedia }" @tap="onSubmit">{{ publishButtonText }}</view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { navigateBack } from '@/utils/nav'
import { createPost, uploadCommunityMedia } from '@/api/community'
import AppNavBar from '@/components/AppNavBar.vue'
import AppIcon from '@/components/AppIcon.vue'
import { useI18nStore } from '@/store/i18n'
import { hasOversizedCommunityImage, isCommunityVideoTooLarge } from '@/utils/community-media'
import { normalizeTempFilePaths } from '@/utils/file-selection'

const { t } = useI18nStore()
type PublishType = 'text' | 'image' | 'video'
type UploadStatus = 'uploading' | 'processing' | 'ready' | 'failed'
interface ImageDraft {
  id: string
  localPath: string
  remoteUrl: string
  status: UploadStatus
  progress: number
}
interface VideoDraft {
  localPath: string
  remoteUrl: string
  duration: number
  status: UploadStatus
  progress: number
}

const type = ref<PublishType>('text')
const submitting = ref(false)
const form = reactive({ content: '', topic: '' })
const imageDrafts = ref<ImageDraft[]>([])
const videoDraft = ref<VideoDraft | null>(null)
const hasUploadingMedia = computed(() => (
  imageDrafts.value.some(item => isMediaBusy(item.status))
  || (videoDraft.value ? isMediaBusy(videoDraft.value.status) : false)
))
const activeUpload = computed(() => imageDrafts.value.find(item => isMediaBusy(item.status))
  || (videoDraft.value && isMediaBusy(videoDraft.value.status) ? videoDraft.value : null))
const publishButtonText = computed(() => {
  if (submitting.value) return t('提交中...')
  if (activeUpload.value?.status === 'processing') return t('mediaProcessing')
  if (activeUpload.value) return t('mediaUploadingProgress', { progress: activeUpload.value.progress })
  return t('发布')
})

function isMediaBusy(status: UploadStatus): boolean {
  return status === 'uploading' || status === 'processing'
}

function mediaStatusText(item: Pick<ImageDraft, 'status' | 'progress'>): string {
  if (item.status === 'processing') return t('mediaProcessing')
  if (item.status === 'uploading') return t('mediaUploadingProgress', { progress: item.progress })
  if (item.status === 'failed') return t('retryUpload')
  return t('mediaUploadReady')
}

function draftId(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

async function uploadImage(item: ImageDraft) {
  item.status = 'uploading'
  item.progress = 0
  item.remoteUrl = ''
  try {
    const result = await uploadCommunityMedia(item.localPath, (progress) => {
      if (!isMediaBusy(item.status)) return
      item.progress = progress
      item.status = progress >= 100 ? 'processing' : 'uploading'
    })
    if (result.kind !== 'image') throw new Error(t('mediaTypeMismatch'))
    item.remoteUrl = result.url
    item.progress = 100
    item.status = 'ready'
  } catch (error) {
    item.status = 'failed'
    uni.showToast({ title: error instanceof Error ? error.message : t('上传失败'), icon: 'none' })
  }
}

async function uploadVideo(item: VideoDraft) {
  item.status = 'uploading'
  item.progress = 0
  item.remoteUrl = ''
  try {
    const result = await uploadCommunityMedia(item.localPath, (progress) => {
      if (!isMediaBusy(item.status)) return
      item.progress = progress
      item.status = progress >= 100 ? 'processing' : 'uploading'
    })
    if (
      result.kind !== 'video'
      || result.content_type !== 'video/mp4'
      || !result.url.toLowerCase().endsWith('.mp4')
      || !result.standardized
      || !Number.isFinite(Number(result.duration))
      || Number(result.duration) <= 0
    ) throw new Error(t('videoStandardizationFailed'))
    item.remoteUrl = result.url
    item.duration = Math.max(1, Math.round(Number(result.duration)))
    item.progress = 100
    item.status = 'ready'
  } catch (error) {
    item.status = 'failed'
    uni.showToast({ title: error instanceof Error ? error.message : t('上传失败'), icon: 'none' })
  }
}

function pickMedia() {
  if (hasUploadingMedia.value) {
    uni.showToast({ title: t('waitMediaUpload'), icon: 'none' })
    return
  }
  if (type.value === 'image') {
    uni.chooseImage({
      count: Math.max(1, 9 - imageDrafts.value.length),
      success: (res) => {
        if (hasOversizedCommunityImage(res.tempFiles)) {
          uni.showToast({ title: t('communityImageTooLarge'), icon: 'none' })
          return
        }
        const paths = normalizeTempFilePaths(res.tempFilePaths)
        paths.slice(0, 9 - imageDrafts.value.length).forEach((localPath) => {
          const item: ImageDraft = { id: draftId(), localPath, remoteUrl: '', status: 'uploading', progress: 0 }
          imageDrafts.value.push(item)
          void uploadImage(item)
        })
      },
    })
  } else {
    uni.chooseVideo({
      extension: ['mp4', 'mov', 'webm'],
      success: (res) => {
        if (isCommunityVideoTooLarge(res.size)) {
          uni.showToast({ title: t('communityVideoTooLarge'), icon: 'none' })
          return
        }
        if (Number(res.duration || 0) > 300) {
          uni.showToast({ title: t('communityVideoTooLong'), icon: 'none' })
          return
        }
        const item: VideoDraft = {
          localPath: res.tempFilePath,
          remoteUrl: '',
          duration: Math.max(0, Math.round(Number(res.duration || 0))),
          status: 'uploading',
          progress: 0,
        }
        videoDraft.value = item
        void uploadVideo(item)
      },
    })
  }
}

function switchType(next: PublishType) {
  if (next === type.value) return
  if (hasUploadingMedia.value) {
    uni.showToast({ title: t('waitMediaUpload'), icon: 'none' })
    return
  }
  type.value = next
}

function removeImage(item: ImageDraft) {
  if (isMediaBusy(item.status)) {
    uni.showToast({ title: t('waitMediaUpload'), icon: 'none' })
    return
  }
  imageDrafts.value = imageDrafts.value.filter(draft => draft.id !== item.id)
}

function removeVideo() {
  if (!videoDraft.value) return
  if (isMediaBusy(videoDraft.value.status)) {
    uni.showToast({ title: t('waitMediaUpload'), icon: 'none' })
    return
  }
  videoDraft.value = null
}

function previewImage(current: string) {
  uni.previewImage({ current, urls: imageDrafts.value.map(item => item.localPath) })
}

function formatDuration(seconds: number): string {
  const safe = Math.max(0, Math.round(seconds || 0))
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, '0')}`
}

async function onSubmit() {
  if (submitting.value) return
  if (!form.content) { uni.showToast({ title: t('请输入内容'), icon: 'none' }); return }
  if (hasUploadingMedia.value) { uni.showToast({ title: t('waitMediaUpload'), icon: 'none' }); return }
  if (type.value === 'image') {
    if (!imageDrafts.value.length) { uni.showToast({ title: t('chooseImageFirst'), icon: 'none' }); return }
    if (imageDrafts.value.some(item => item.status === 'failed')) {
      uni.showToast({ title: t('retryFailedMedia'), icon: 'none' }); return
    }
  }
  if (type.value === 'video') {
    if (!videoDraft.value) { uni.showToast({ title: t('chooseVideoFirst'), icon: 'none' }); return }
    if (videoDraft.value.status === 'failed') {
      uni.showToast({ title: t('retryFailedMedia'), icon: 'none' }); return
    }
    if (!videoDraft.value.duration) {
      uni.showToast({ title: t('invalidVideoDuration'), icon: 'none' }); return
    }
  }
  submitting.value = true
  try {
    await createPost({
      content: form.content,
      images: type.value === 'image' ? imageDrafts.value.map(item => item.remoteUrl) : undefined,
      video: type.value === 'video' ? videoDraft.value?.remoteUrl : undefined,
      video_duration: type.value === 'video' ? videoDraft.value?.duration : undefined,
      topic: form.topic || undefined,
    })
    uni.showToast({ title: t('发布成功'), icon: 'success' })
    setTimeout(() => navigateBack(), 800)
  } catch {
    submitting.value = false
    return
  }
  submitting.value = false
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.type-row { display: flex; gap: 16rpx; margin: 24rpx 0; }
.type-i { flex: 1; text-align: center; padding: 20rpx 0; border: 1rpx solid var(--border); border-radius: var(--radius); color: var(--text-sub); font-size: 26rpx; background: var(--card); }
.type-i.active { border-color: var(--primary); color: var(--primary); background: var(--card-border); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); padding: 32rpx; }
.tarea { width: 100%; min-height: 240rpx; color: var(--text); font-size: 28rpx; line-height: 1.6; }
.ph { color: var(--text-dim); }
.media-pick { display: flex; flex-direction: column; align-items: center; padding: 40rpx; border: 2rpx dashed var(--border); border-radius: var(--radius); margin: 24rpx 0; }
.mp-text { color: var(--text-sub); font-size: 24rpx; margin-top: 12rpx; }
.media-limit { color: var(--text-dim); font-size: 20rpx; margin-top: 8rpx; }
.image-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12rpx; margin: 24rpx 0; }
.image-cell { position: relative; aspect-ratio: 1; overflow: hidden; border-radius: 14rpx; background: var(--bg); }
.image-preview { width: 100%; height: 100%; display: block; }
.remove-media { position: absolute; z-index: 3; top: 8rpx; right: 8rpx; width: 40rpx; height: 40rpx; border-radius: 50%; color: #fff; background: rgba(0,0,0,0.64); display: flex; align-items: center; justify-content: center; font-size: 30rpx; }
.remove-media.disabled, .remove-text.disabled { opacity: 0.42; }
.media-state { position: absolute; z-index: 2; inset: 0; display: flex; flex-direction: column; gap: 14rpx; align-items: center; justify-content: center; color: #fff; background: rgba(17,24,39,0.62); font-size: 22rpx; font-weight: 600; }
.media-progress, .video-progress { height: 6rpx; overflow: hidden; background: rgba(255,255,255,0.24); }
.media-progress { width: 72%; border-radius: 999rpx; }
.media-progress view, .video-progress view { height: 100%; border-radius: inherit; background: var(--primary); transition: width 0.18s ease; }
.video-preview-wrap { margin: 24rpx 0; overflow: hidden; border: 1rpx solid var(--border); border-radius: var(--radius); }
.video-preview { width: 100%; height: 360rpx; display: block; background: #111827; }
.video-meta { min-height: 72rpx; padding: 0 20rpx; display: flex; align-items: center; gap: 18rpx; color: var(--text-sub); font-size: 22rpx; }
.uploading-text { margin-left: auto; color: var(--primary); }
.failed-text { margin-left: auto; color: var(--down); font-weight: 600; }
.ready-text { margin-left: auto; color: var(--up); }
.remove-text { color: var(--text-dim); }
.video-progress { width: 100%; }
.topic-row { display: flex; align-items: center; gap: 16rpx; padding-top: 24rpx; border-top: 1rpx solid var(--divider); }
.topic-t { color: var(--primary); font-size: 26rpx; }
.topic-i { flex: 1; color: var(--text); font-size: 26rpx; }
.btn-primary { background: linear-gradient(135deg, var(--primary), var(--primary)); color: #fff; text-align: center; padding: 28rpx 0; border-radius: var(--radius); font-size: 30rpx; font-weight: 600; margin-top: 32rpx; }
.btn-primary.disabled { opacity: 0.4; }
</style>
