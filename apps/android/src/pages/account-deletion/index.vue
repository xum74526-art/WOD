<template>
  <view class="page">
    <AppNavBar :title="t('accountDeletion')" :showBack="!receiptView" />
    <scroll-view scroll-y class="body">
      <view v-if="receiptView" class="card section">
        <text class="heading">{{ t(state.stage === 'completed' ? 'deletionCompleted' : state.stage === 'processing' ? 'deletionProcessing' : 'deletionStatusUnknown') }}</text>
        <text class="paragraph">{{ t(state.stage === 'completed' ? 'deletionCompletedHint' : state.stage === 'processing' ? 'deletionProcessingHint' : 'deletionStatusUnknownHint') }}</text>
        <text v-if="state.stage === 'verified'" class="paragraph">{{ t('deletionNotSubmitted') }}</text>
        <text v-if="receiptExpired" class="paragraph">{{ t('deletionReceiptExpired') }}</text>
        <text v-if="state.stage === 'processing' && state.blockers.length" class="paragraph">{{ t('deletionProcessingBlocked') }}</text>
        <view v-for="blocker in state.blockers" :key="blocker.code" class="blocker">
          <text>{{ tr(blocker.message) }}</text>
          <text v-if="blocker.count > 0">{{ t('deletionItemCount', { count: blocker.count }) }}</text>
        </view>
        <text v-if="state.completedAt" class="paragraph">{{ t('deletionCompletedTime', { time: state.completedAt }) }}</text>
        <button v-if="state.stage !== 'completed'" class="action" :disabled="state.busy || !state.ticket" @tap="checkStatus">{{ t(state.busy ? 'loading' : 'deletionCheckStatus') }}</button>
        <template v-if="state.stage === 'verified'">
          <checkbox-group @change="onAcknowledgement">
            <label class="acknowledgement retry-acknowledgement">
              <checkbox value="understood" :checked="acknowledged" :disabled="state.busy" color="#18AFC4" />
              <text>{{ t('deletionAcknowledgement') }}</text>
            </label>
          </checkbox-group>
          <button class="action danger" :disabled="state.busy || !acknowledged" @tap="showConfirm = true">{{ t('deletionRetrySameRequest') }}</button>
          <button v-if="userStore.isLogin && canReverify" class="secondary" :disabled="state.busy" @tap="restartExpiredVerification">{{ t('deletionReverifyExpired') }}</button>
        </template>
        <button class="secondary" @tap="goLogin">{{ t('deletionBackToLogin') }}</button>
      </view>

      <template v-else>
        <view class="card section">
          <text class="heading">{{ t('deletionBeforeTitle') }}</text>
          <text class="paragraph">{{ t('deletionImpact') }}</text>
          <text class="paragraph">{{ t('deletionRetention') }}</text>
          <text class="paragraph">{{ t('deletionKaiBinding') }}</text>
          <text class="link" @tap="nav('/pages/agreement/index?type=privacy')">{{ t('隐私政策') }}</text>
        </view>
        <view v-if="!userStore.isLogin" class="card section">
          <text class="paragraph">{{ t('deletionLoginRequired') }}</text>
          <button class="action" @tap="goLogin">{{ t('登录') }}</button>
        </view>
        <template v-else>
          <view class="card section">
            <text class="heading">{{ t('deletionEligibilityTitle') }}</text>
            <text class="paragraph">{{ t(state.eligibility?.eligible && !state.blockers.length ? 'deletionEligible' : 'deletionEligibilityHint') }}</text>
            <view v-for="blocker in state.blockers" :key="blocker.code" class="blocker">
              <text>{{ tr(blocker.message) }}</text>
              <text v-if="blocker.count > 0">{{ t('deletionItemCount', { count: blocker.count }) }}</text>
            </view>
            <button class="secondary" :disabled="state.busy" @tap="refreshEligibility">{{ t(state.busy ? 'loading' : 'deletionRecheck') }}</button>
          </view>
          <view v-if="state.eligibility?.automatic_actions.length" class="card section">
            <text class="heading">{{ t('deletionAutomaticActions') }}</text>
            <text v-for="action in state.eligibility.automatic_actions" :key="action" class="paragraph">{{ tr(action) }}</text>
          </view>
          <view v-if="state.eligibility?.eligible && !state.blockers.length" class="card section">
            <checkbox-group @change="onAcknowledgement">
              <label class="acknowledgement">
                <checkbox value="understood" :checked="acknowledged" :disabled="state.busy" color="#18AFC4" />
                <text>{{ t('deletionAcknowledgement') }}</text>
              </label>
            </checkbox-group>
            <text class="field-label">{{ t('deletionPasswordLabel') }}</text>
            <input v-model="password" class="password" password :maxlength="128" :disabled="state.busy" :placeholder="t('deletionPasswordPlaceholder')" />
            <text class="paragraph muted">{{ t('deletionPasswordHint') }}</text>
            <button class="action danger" :disabled="!canVerify" @tap="verifyPassword">{{ t(state.busy ? 'loading' : 'deletionVerifyContinue') }}</button>
          </view>
        </template>
      </template>
      <view v-if="error" class="error" role="alert">{{ error }}</view>
    </scroll-view>
    <ConfirmSheet :visible="showConfirm" :title="t('deletionFinalTitle')" :desc="t('deletionFinalHint')"
      :cancelText="t('cancel')" :confirmText="t('deletionConfirm')" @cancel="cancelConfirmation" @confirm="confirmDeletion" />
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { onBackPress, onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '@/components/AppNavBar.vue'
import ConfirmSheet from '@/components/ConfirmSheet.vue'
import { getDeletionEligibility, getDeletionStatus, submitAccountDeletion, verifyDeletionPassword } from '@/api/account-deletion'
import { ApiRequestError } from '@/api/request'
import { createDeletionController, createDeletionState } from '@/utils/account-deletion'
import { clearDeletionReceipt, consumeDeletionCompletion, readDeletionReceipt, rememberDeletionCompletion, saveDeletionReceipt } from '@/utils/account-deletion-receipt'
import { clearInquiryRequestPrefill } from '@/utils/inquiry-request'
import { navigateTo as nav } from '@/utils/nav'
import { useUserStore } from '@/store/user'
import { useNotificationStore } from '@/store/notification'
import { useI18nStore } from '@/store/i18n'

const { t, tr } = useI18nStore()
const userStore = useUserStore()
const state = reactive(createDeletionState())
const password = ref('')
const acknowledged = ref(false)
const showConfirm = ref(false)
const error = ref('')
const canReverify = ref(false)
const receiptExpired = ref(false)
const receiptView = computed(() => ['uncertain', 'processing', 'completed'].includes(state.stage) || (state.hasSubmitted && state.stage === 'verified') || (state.hasSubmitted && state.stage === 'blocked' && !userStore.isLogin))
const canVerify = computed(() => !state.busy && acknowledged.value && !!password.value && !!state.eligibility?.eligible)
let pollTimer: ReturnType<typeof setTimeout> | null = null
let polls = 0
let active = true
let needsPageReset = false

const controller = createDeletionController({
  state, eligibility: getDeletionEligibility, verify: verifyDeletionPassword,
  submit: submitAccountDeletion, status: getDeletionStatus,
  saveReceipt: saveDeletionReceipt, clearReceipt: clearDeletionReceipt,
  ownerUserId: () => userStore.userInfo?.id,
  clearSession(ownerUserId) {
    // An old A receipt must not sign out a newly logged-in B account. Legacy
    // receipts without an owner may query status but never clear a live session.
    if (!ownerUserId || userStore.userInfo?.id !== ownerUserId) return
    needsPageReset = true
    userStore.logout()
    clearInquiryRequestPrefill()
    for (const key of ['wod_kai_callback_fingerprint', 'wod_kai_bind_callback_fingerprint', 'wod_kai_auth_intent']) uni.removeStorageSync(key)
  },
})

function showError(cause: unknown) {
  error.value = cause instanceof Error ? tr(t(cause.message)) : t('deletionNetworkError')
}
function onAcknowledgement(event: { detail: { value: string[] } }) {
  acknowledged.value = event.detail.value.includes('understood')
}
function cancelConfirmation() {
  showConfirm.value = false
  if (state.hasSubmitted) return
  state.ticket = ''
  state.stage = 'review'
}
async function refreshEligibility() {
  if (state.busy) return
  error.value = ''
  acknowledged.value = false
  canReverify.value = false
  password.value = ''
  try { await controller.checkEligibility() } catch (cause) { showError(cause) }
}
async function verifyPassword() {
  if (!canVerify.value) return
  error.value = ''
  try {
    await controller.verify(password.value)
    showConfirm.value = state.stage === 'verified'
  } catch (cause) { showError(cause) }
  finally { password.value = '' }
}
async function confirmDeletion() {
  if (!showConfirm.value || state.busy || !acknowledged.value) return
  showConfirm.value = false
  error.value = ''
  useNotificationStore().stopPolling()
  try { await controller.submit() } catch (cause) {
    showError(cause)
    if (cause instanceof Error && cause.message === 'deletionVerificationExpired') canReverify.value = true
    if (cause instanceof ApiRequestError && cause.statusCode === 400) {
      // Only a definitive server rejection (never a timeout) permits a fresh
      // verification, and only after status confirms no deletion has started.
      canReverify.value = true
      try { await controller.checkStatus() } catch { /* Keep the same receipt and original error. */ }
    }
  }
  if (state.stage === 'blocked') acknowledged.value = false
  if (userStore.isLogin && state.stage !== 'uncertain') useNotificationStore().startPolling()
  if (resetDeletedNavigation()) return
  schedulePoll()
}
async function checkStatus() {
  if (state.busy) return
  error.value = ''
  try {
    await controller.checkStatus()
    if (state.stage === 'verified') {
      // A delayed original submission can still arrive. Keep its capability,
      // and let the user explicitly confirm a same-ticket retry if necessary.
      acknowledged.value = false
    }
  } catch (cause) {
    showError(cause)
    if (cause instanceof ApiRequestError && cause.statusCode === 401) {
      // An invalid capability is not a completed deletion. Remove only this
      // expired credential and leave an explicit, non-success status message.
      clearDeletionReceipt(state.ticket)
      state.ticket = ''
      receiptExpired.value = true
    }
  }
  if (resetDeletedNavigation()) return
  schedulePoll()
}
function resetDeletedNavigation() {
  if (!needsPageReset) return false
  needsPageReset = false
  if (state.stage === 'completed') rememberDeletionCompletion({ status: 'completed', blockers: [], completed_at: state.completedAt })
  // Clear cached order/profile pages from the navigation stack. Processing
  // recovers via the existing capability; completion uses a one-shot notice.
  uni.reLaunch({ url: '/pages/account-deletion/index' })
  return true
}
async function restartExpiredVerification() {
  if (state.busy || state.stage !== 'verified' || !userStore.isLogin || !canReverify.value) return
  // This is a separate, explicit action after the server reported verified;
  // never discard a processing/unknown request to start a second request.
  clearDeletionReceipt(state.ticket)
  await refreshEligibility()
}
function stopPoll() {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = null
}
function schedulePoll() {
  stopPoll()
  if (!active || state.stage !== 'processing' || polls >= 6) return
  pollTimer = setTimeout(() => { polls += 1; void checkStatus() }, 5000)
}
function goLogin() { uni.reLaunch({ url: '/pages/login/index' }) }
onLoad(() => {
  const completed = consumeDeletionCompletion()
  if (completed) {
    state.stage = 'completed'
    state.completedAt = completed.completed_at
    return
  }
  const receipt = readDeletionReceipt()
  if (receipt) { controller.restore(receipt); void checkStatus() }
  else if (userStore.isLogin) void refreshEligibility()
})
onShow(() => { active = true; schedulePoll() })
onHide(() => { active = false; password.value = ''; showConfirm.value = false; stopPoll() })
onUnload(() => { active = false; password.value = ''; state.ticket = ''; stopPoll() })
onBackPress(() => {
  if (!receiptView.value) return false
  goLogin()
  return true
})
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.body { flex: 1; box-sizing: border-box; padding: 24rpx 32rpx calc(64rpx + var(--safe-bottom)); }
.section { margin-bottom: 24rpx; padding: 30rpx; }
.heading { display: block; font-size: 30rpx; font-weight: 600; color: var(--text); }
.paragraph { display: block; margin-top: 18rpx; font-size: 26rpx; line-height: 1.7; color: var(--text); }
.muted { color: var(--text-sub); font-size: 24rpx; }
.link { display: block; margin-top: 20rpx; color: var(--primary); font-size: 26rpx; }
.blocker { margin-top: 18rpx; padding: 20rpx; background: var(--down-soft); color: var(--down); font-size: 26rpx; line-height: 1.6; display: flex; flex-direction: column; }
.acknowledgement { display: flex; align-items: flex-start; gap: 12rpx; font-size: 26rpx; line-height: 1.6; color: var(--text); }
.retry-acknowledgement { margin-top: 26rpx; }
.field-label { display: block; margin: 30rpx 0 16rpx; font-size: 26rpx; color: var(--text); }
.password { padding: 22rpx; border: 1rpx solid var(--border); border-radius: 12rpx; font-size: 28rpx; height: auto; background: var(--bg); }
.action, .secondary { margin-top: 26rpx; padding: 26rpx; border-radius: 16rpx; font-size: 28rpx; line-height: 1.4; }
.action { background: var(--primary); color: #fff; }
.danger { background: var(--down); }
.action[disabled], .secondary[disabled] { opacity: .45; }
.secondary { background: var(--bg); border: 1rpx solid var(--border); color: var(--text); }
.error { margin-bottom: 24rpx; padding: 24rpx; color: var(--down); background: var(--down-soft); border-radius: 16rpx; font-size: 26rpx; line-height: 1.6; }
</style>
