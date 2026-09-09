<template>
  <view class="page">
    <AppNavBar :title="t('realName')" />
    <view class="shell">
      <view v-if="loading" class="load-state">{{ t('loading') }}</view>
      <view v-else-if="loadError" class="load-state load-error">
        <text>{{ t('dataUnavailable') }}</text>
        <view class="load-retry" role="button" @tap="load(false)">{{ t('retry') }}</view>
      </view>
      <template v-else>
      <view v-if="info?.status === 'verified'" class="card status-card ok">
        <text class="st-icon">✓</text>
        <text class="st-title">{{ t('k_6eaa1495') }}</text>
        <text class="st-sub">{{ info?.real_name }} · {{ maskId }}</text>
      </view>
      <view v-else-if="info?.status === 'pending'" class="card status-card" :class="ocrStatusClass">
        <view v-if="ocrStatus === 'processing'" class="status-progress" aria-hidden="true">
          <view class="status-progress-bar"></view>
        </view>
        <text class="st-title">{{ pendingTitle }}</text>
        <text class="st-sub">{{ pendingDescription }}</text>
        <view v-if="ocrStatus === 'processing'" class="status-refresh" role="button" @tap="load(false)">{{ t('refreshOcrStatus') }}</view>
      </view>
      <view v-else-if="info?.status === 'rejected'" class="card status-card bad">
        <text class="st-title">{{ t('k_3daea60a') }}</text>
        <text class="st-sub">{{ tr(info?.reject_reason || '请重新提交') }}</text>
      </view>
      <view v-else class="card status-card">
        <text class="st-title">{{ t('k_e1fcc629') }}</text>
        <text class="st-sub">{{ t('k_7f43de98') }}</text>
      </view>

      <view v-if="showOcrPanel" class="card ocr-card">
        <view class="ocr-head">
          <view>
            <text class="ocr-title">{{ t('ocrPrecheckTitle') }}</text>
            <text class="ocr-caption">{{ t('ocrPrecheckPrivacyCaption') }}</text>
          </view>
          <text class="ocr-badge" :class="ocrStatusClass">{{ ocrStatusLabel }}</text>
        </view>
        <view v-if="ocrStatus === 'processing'" class="ocr-skeleton" aria-hidden="true">
          <view v-for="index in 5" :key="index" class="ocr-skeleton-row"><view></view><view></view></view>
        </view>
        <view v-else-if="ocrSummaryRows.length" class="ocr-summary">
          <view v-for="row in ocrSummaryRows" :key="row.key" class="ocr-row">
            <text>{{ t(row.label) }}</text>
            <text class="ocr-result" :class="row.resultClass">{{ row.resultLabel }}</text>
          </view>
        </view>
        <text class="ocr-note">{{ ocrStatusDescription }}</text>
        <view v-if="ocrRetryable" class="ocr-retry">
          <text class="ocr-retry-hint">{{ t('ocrRetakeHint') }}</text>
          <view class="ocr-retry-button" :class="{ disabled: submitting }" role="button" @tap="retryOcr">{{ t('retryOcrRecognition') }}</view>
        </view>
      </view>

      <SectionHeader :title="t('k_cbaa044e')" v-if="info?.status !== 'verified'" />
      <view class="card form" v-if="info?.status !== 'verified'">
        <view class="field">
          <text class="flabel">{{ t('k_7eacb4d9') }}</text>
          <input class="finput" v-model="form.real_name" :placeholder="t('k_95cce537')" placeholder-class="ph" />
        </view>
        <view class="field">
          <text class="flabel">{{ t('k_32ffa250') }}</text>
          <input class="finput" v-model="form.id_card" :placeholder="t('k_c415a36b')" placeholder-class="ph" maxlength="18" />
        </view>

        <SectionHeader :title="t('k_4a3b0a19')" />
        <view class="photo-row">
          <view class="photo-box" @tap="choosePhoto('front')">
            <image v-if="frontPhoto" class="photo-img" :src="frontPhoto" mode="aspectFill" />
            <view v-else class="photo-placeholder">
              <AppIcon name="plus" :size="48" />
              <text class="photo-label">{{ t('k_18b08c74') }}</text>
            </view>
          </view>
          <view class="photo-box" @tap="choosePhoto('back')">
            <image v-if="backPhoto" class="photo-img" :src="backPhoto" mode="aspectFill" />
            <view v-else class="photo-placeholder">
              <AppIcon name="plus" :size="48" />
              <text class="photo-label">{{ t('k_080453c7') }}</text>
            </view>
          </view>
        </view>

        <checkbox-group @change="onOcrConsentChange">
          <label class="ocr-consent">
            <checkbox value="accepted" :checked="ocrConsent" color="#18afc4" />
            <text>{{ t('localOcrConsent') }}</text>
          </label>
        </checkbox-group>
        <view v-if="submissionError" class="submit-error">
          <text>{{ submissionError }}</text>
          <view class="submit-error-retry" role="button" @tap="onSubmit">{{ t('retrySubmission') }}</view>
        </view>
        <view class="btn-primary" :class="{ disabled: submitting }" @tap="onSubmit">
          <text>{{ submitButtonLabel }}</text>
        </view>
      </view>
      <view class="risk">{{ t('k_dbb737eb') }}</view>
      </template>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { onHide, onShow, onUnload } from '@dcloudio/uni-app'
import {
  getVerification,
  submitVerification,
  uploadVerificationPhotos,
  type VerificationInfo,
} from '@/api/verification'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import AppIcon from '@/components/AppIcon.vue'
import { useI18nStore } from '@/store/i18n'
import {
  OCR_SUMMARY_FIELDS,
  hasOcrResult,
  isOcrRetryable,
  normalizeOcrStatus,
  ocrSummaryValue,
  shouldPollOcr,
} from '@/utils/verification-ocr'
import { normalizeTempFilePaths } from '@/utils/file-selection'

const { t, tr } = useI18nStore()
const info = ref<VerificationInfo | null>(null)
const loading = ref(true)
const loadError = ref(false)
const submitting = ref(false)
const submitPhase = ref<'idle' | 'submitting' | 'uploading' | 'processing'>('idle')
const submissionError = ref('')
const ocrConsent = ref(false)
const form = reactive({ real_name: '', id_card: '' })
const frontPhoto = ref('')
const backPhoto = ref('')
let ocrPollTimer: ReturnType<typeof setTimeout> | null = null
let ocrPollAttempts = 0

const maskId = computed(() => {
  return info.value?.id_card_masked || ''
})

const ocrStatus = computed(() => normalizeOcrStatus(info.value?.ocr_status))
const showOcrPanel = computed(() => hasOcrResult(info.value))
const ocrRetryable = computed(() => isOcrRetryable(ocrStatus.value))
const ocrStatusClass = computed(() => ocrStatus.value ? `ocr-${ocrStatus.value}` : 'ocr-not-started')
const pendingTitle = computed(() => {
  if (ocrStatus.value === 'processing') return t('ocrProcessingTitle')
  if (ocrStatus.value === 'matched') return t('ocrMatchedPendingReview')
  if (ocrStatus.value === 'review_required') return t('ocrManualReviewRequired')
  if (ocrStatus.value === 'error' || ocrStatus.value === 'unavailable') return t('ocrRecognitionIncomplete')
  return t('k_b720a69a')
})
const pendingDescription = computed(() => {
  if (ocrStatus.value === 'processing') return t('ocrProcessingDescription')
  if (ocrStatus.value === 'matched') return t('ocrMatchedDescription')
  if (ocrStatus.value === 'review_required') return t('ocrManualReviewDescription')
  if (ocrStatus.value === 'error' || ocrStatus.value === 'unavailable') return t('ocrRetryDescription')
  return t('k_f73fb47b')
})
const ocrStatusLabel = computed(() => t(`ocrStatus_${ocrStatus.value || 'not_started'}`))
const ocrStatusDescription = computed(() => {
  if (ocrStatus.value === 'matched') return t('ocrMatchedPrivacyDescription')
  if (ocrStatus.value === 'review_required') return t('ocrManualReviewDescription')
  if (ocrStatus.value === 'error') return t('ocrErrorDescription')
  if (ocrStatus.value === 'unavailable') return t('ocrUnavailableDescription')
  if (ocrStatus.value === 'processing') return t('ocrProcessingDescription')
  return t('ocrWaitingDescription')
})
const ocrSummaryRows = computed(() => OCR_SUMMARY_FIELDS.map((field) => {
  const result = ocrSummaryValue(info.value?.ocr_summary, field.key)
  const resultKey = result === null
    ? 'ocrMatchPending'
    : field.resultType === 'validity'
      ? result ? 'ocrValidityValid' : 'ocrValidityInvalid'
      : result ? 'ocrMatchYes' : 'ocrMatchNo'
  return {
    ...field,
    resultLabel: t(resultKey),
    resultClass: result === true ? 'matched' : result === false ? 'mismatched' : 'pending',
  }
}))
const submitButtonLabel = computed(() => {
  if (submitPhase.value === 'submitting') return t('submittingIdentityData')
  if (submitPhase.value === 'uploading') return t('uploadingIdPhotos')
  if (submitPhase.value === 'processing') return t('startingOcrRecognition')
  return t('提交认证')
})

function clearOcrPoll() {
  if (ocrPollTimer) clearTimeout(ocrPollTimer)
  ocrPollTimer = null
}

function scheduleOcrPoll() {
  clearOcrPoll()
  if (!shouldPollOcr(ocrStatus.value) || ocrPollAttempts >= 8) return
  ocrPollTimer = setTimeout(() => {
    ocrPollAttempts += 1
    void load(true)
  }, 2500)
}

async function load(silent = false) {
  if (!silent) loading.value = true
  loadError.value = false
  try {
    info.value = await getVerification()
    if (!form.real_name && info.value?.real_name) form.real_name = info.value.real_name
    scheduleOcrPoll()
  }
  catch { if (!silent) loadError.value = true }
  finally { if (!silent) loading.value = false }
}
onShow(() => {
  ocrPollAttempts = 0
  void load()
})
onHide(clearOcrPoll)
onUnload(clearOcrPoll)

function choosePhoto(side: 'front' | 'back') {
  uni.chooseImage({
    count: 1,
    success: (res) => {
      submissionError.value = ''
      const [selectedPath] = normalizeTempFilePaths(res.tempFilePaths)
      if (!selectedPath) return
      if (side === 'front') frontPhoto.value = selectedPath
      else backPhoto.value = selectedPath
    },
  })
}

function onOcrConsentChange(event: { detail: { value: string[] } }) {
  ocrConsent.value = event.detail.value.includes('accepted')
}

async function onSubmit() {
  if (submitting.value) return
  submissionError.value = ''
  if (!ocrConsent.value) {
    uni.showToast({ title: t('localOcrConsentRequired'), icon: 'none' })
    return
  }
  // 校验姓名
  if (!/^[\u4e00-\u9fa5]{2,10}$/.test(form.real_name)) {
    uni.showToast({ title: t('姓名须为2-10位中文'), icon: 'none' }); return
  }
  // 校验身份证号（18位，前17位数字+数字或X）
  const id = form.id_card.trim().toUpperCase()
  if (!/^\d{17}[\dX]$/.test(id)) {
    uni.showToast({ title: t('身份证号须18位'), icon: 'none' }); return
  }
  if (!frontPhoto.value || !backPhoto.value) {
    uni.showToast({ title: t('请上传身份证正反面照片'), icon: 'none' }); return
  }
  submitting.value = true

  try {
    submitPhase.value = 'submitting'
    await submitVerification(form.real_name, id, true)
    submitPhase.value = 'uploading'
    const completed = await uploadPhotos()
    info.value = completed
    submitPhase.value = 'processing'
    uni.showToast({ title: t('identitySubmittedForOcr'), icon: 'success' })
    ocrPollAttempts = 0
    await load()
  } catch (error) {
    const message = error instanceof Error && error.message ? tr(error.message) : t('上传失败')
    submissionError.value = message
    uni.showToast({ title: message, icon: 'none' })
  } finally {
    submitting.value = false
    submitPhase.value = 'idle'
  }
}

async function uploadPhotos(): Promise<VerificationInfo> {
  const completed = await uploadVerificationPhotos(frontPhoto.value, backPhoto.value)
  if (!completed.front_photo_uploaded || !completed.back_photo_uploaded) {
    throw new Error(t('请上传身份证正反面照片'))
  }
  return completed
}

async function retryOcr() {
  // 旧的待审记录可能尚未保存敏感信息处理同意；重试必须先重新提交资料和明确同意。
  await onSubmit()
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; min-height: 100dvh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--border); }
.load-state { min-height: 360rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 26rpx; }
.load-error { flex-direction: column; gap: 18rpx; }
.load-retry { min-height: 68rpx; padding: 0 28rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: var(--radius); font-weight: 700; }
.status-card { padding: 48rpx 32rpx; text-align: center; margin: 24rpx 0; }
.st-icon { font-size: 64rpx; color: var(--up); }
.st-title { display: block; color: var(--text); font-size: 34rpx; font-weight: 700; margin: 16rpx 0 12rpx; }
.st-sub { display: block; color: var(--text-sub); font-size: 26rpx; }
.status-card.ok { background: rgba(22,163,74,0.06); border-color: rgba(22,163,74,0.2); }
.status-card.bad { background: var(--down-soft); border-color: rgba(239,68,68,0.2); }
.status-card.ocr-matched { background: rgba(22,163,74,.06); border-color: rgba(22,163,74,.2); }
.status-card.ocr-review_required, .status-card.ocr-error { background: rgba(245,158,11,.07); border-color: rgba(245,158,11,.24); }
.status-progress { width: 160rpx; height: 8rpx; margin: 0 auto 18rpx; overflow: hidden; background: var(--primary-soft); border-radius: 999rpx; }
.status-progress-bar { width: 45%; height: 100%; background: var(--primary); border-radius: inherit; animation: status-scan 1.4s ease-in-out infinite alternate; }
.status-refresh { min-height: 64rpx; margin: 22rpx auto 0; padding: 0 24rpx; display: inline-flex; align-items: center; justify-content: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: 14rpx; font-size: 22rpx; font-weight: 700; }

.ocr-card { padding: 26rpx 28rpx; margin-bottom: 24rpx; }
.ocr-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20rpx; }
.ocr-title { display: block; color: var(--text); font-size: 28rpx; font-weight: 750; }
.ocr-caption { display: block; max-width: 450rpx; margin-top: 7rpx; color: var(--text-dim); font-size: 20rpx; line-height: 1.45; }
.ocr-badge { flex: none; padding: 8rpx 14rpx; color: var(--text-sub); background: var(--bg-2); border-radius: 12rpx; font-size: 19rpx; font-weight: 700; }
.ocr-badge.ocr-processing { color: var(--primary); background: var(--primary-soft); }
.ocr-badge.ocr-matched { color: #15803d; background: rgba(22,163,74,.1); }
.ocr-badge.ocr-review_required, .ocr-badge.ocr-error { color: #a16207; background: rgba(245,158,11,.12); }
.ocr-summary { margin-top: 20rpx; border-top: 1rpx solid var(--divider); }
.ocr-row { min-height: 66rpx; display: flex; align-items: center; justify-content: space-between; color: var(--text-sub); font-size: 22rpx; border-bottom: 1rpx solid var(--divider); }
.ocr-result { font-weight: 750; }
.ocr-result.matched { color: #15803d; }
.ocr-result.mismatched { color: var(--down); }
.ocr-result.pending { color: var(--text-dim); }
.ocr-note { display: block; margin-top: 18rpx; color: var(--text-sub); font-size: 21rpx; line-height: 1.55; }
.ocr-retry { margin-top: 18rpx; padding-top: 18rpx; border-top: 1rpx solid var(--divider); }
.ocr-retry-hint { display: block; color: var(--text-sub); font-size: 21rpx; line-height: 1.5; }
.ocr-retry-button { min-height: 68rpx; margin-top: 14rpx; display: flex; align-items: center; justify-content: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: 14rpx; font-size: 22rpx; font-weight: 750; }
.ocr-retry-button.disabled { opacity: .4; }
.ocr-skeleton { margin-top: 20rpx; border-top: 1rpx solid var(--divider); }
.ocr-skeleton-row { min-height: 66rpx; display: flex; align-items: center; justify-content: space-between; border-bottom: 1rpx solid var(--divider); }
.ocr-skeleton-row view { width: 150rpx; height: 18rpx; border-radius: 6rpx; background: var(--bg-2); }
.ocr-skeleton-row view:last-child { width: 74rpx; }
.form { padding: 16rpx 32rpx; margin-bottom: 24rpx; }
.field { margin-bottom: 32rpx; }
.flabel { color: var(--text-sub); font-size: 24rpx; display: block; margin-bottom: 12rpx; }
.finput { color: var(--text); font-size: 32rpx; }
.ph { color: var(--text-dim); }

.photo-row { display: flex; gap: 20rpx; margin-bottom: 32rpx; }
.photo-box { width: 50%; aspect-ratio: 1.6; border-radius: var(--radius); border: 1rpx dashed var(--border); overflow: hidden; }
.photo-img { width: 100%; height: 100%; }
.photo-placeholder { width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12rpx; }
.photo-label { color: var(--text-dim); font-size: 22rpx; }
.ocr-consent { display: flex; align-items: flex-start; gap: 12rpx; margin: 0 0 22rpx; color: var(--text-sub); font-size: 21rpx; line-height: 1.55; }
.ocr-consent checkbox { flex: none; margin-top: 2rpx; transform: scale(.82); transform-origin: top left; }

.btn-primary { background: var(--primary); color: #fff; text-align: center; padding: 28rpx 0; border-radius: var(--radius); font-size: 30rpx; font-weight: 600; }
.btn-primary.disabled { opacity: 0.4; }
.submit-error { display: flex; align-items: center; justify-content: space-between; gap: 18rpx; margin: 0 0 20rpx; padding: 18rpx 20rpx; color: var(--down); background: var(--down-soft); border-radius: 14rpx; font-size: 21rpx; line-height: 1.45; }
.submit-error-retry { flex: none; min-height: 54rpx; padding: 0 16rpx; display: flex; align-items: center; border: 1rpx solid var(--down); border-radius: 12rpx; font-weight: 700; }
.risk { color: var(--text-dim); font-size: 22rpx; padding: 16rpx 8rpx; line-height: 1.6; }

@keyframes status-scan { from { transform: translateX(0); } to { transform: translateX(122%); } }
@media (prefers-reduced-motion: reduce) { .status-progress-bar { animation: none; width: 100%; opacity: .55; } }
</style>
