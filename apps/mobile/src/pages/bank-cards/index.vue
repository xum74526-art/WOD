<template>
  <view class="page">
    <AppNavBar :title="t('bankCard')" />
    <scroll-view scroll-y class="shell">
      <view class="notice-card">
        <text class="notice-title">{{ t('bankCardRegistrationTitle') }}</text>
        <text class="notice-text">{{ t('bankCardRegistrationNotice') }}</text>
      </view>

      <view v-if="verification && verification.status !== 'verified'" class="verify-card">
        <view>
          <text class="verify-title">{{ t(verification.status === 'pending' ? 'identityReviewPending' : 'identityRequiredForBankCard') }}</text>
          <text class="verify-text">{{ t(verification.status === 'pending' ? 'bankCardMayBeSubmittedWhileIdentityPending' : 'completeIdentityBeforeBankApproval') }}</text>
        </view>
        <text v-if="verification.status !== 'pending'" class="verify-link" @tap="goVerification">{{ t('goVerify') }}</text>
      </view>

      <view v-if="!bindingEnabled" class="service-warning">{{ t('bankCardBindingUnavailable') }}</view>
      <view v-if="loading" class="state">{{ t('loading') }}</view>
      <view v-else-if="loadError" class="load-error">
        <text>{{ t('listLoadFailedDesc') }}</text>
        <text class="load-retry" @tap="load">{{ t('retry') }}</text>
      </view>
      <view v-else-if="!list.length" class="card empty-card"><EmptyState :text="t('noBankCards')" /></view>

      <view v-for="card in list" :key="card.id" class="card bank-card" :class="`status-${card.status}`">
        <view class="card-top">
          <view>
            <text class="bank-name">{{ tr(card.bank_name) }}</text>
            <text class="card-number">{{ card.card_number }}</text>
          </view>
          <text class="status-badge" :class="cardStatusTone(card.status)">{{ t(bankCardStatusLabel(card.status)) }}</text>
        </view>
        <view class="card-meta">
          <text>{{ t('cardholderValue', { name: card.holder }) }}</text>
          <text v-if="card.phone">{{ t('reservedPhoneValue', { phone: card.phone }) }}</text>
        </view>
        <text v-if="!isRegisteredStatus(card.status) && card.reject_reason" class="reject-reason">{{ t('reviewReasonValue', { reason: tr(card.reject_reason) }) }}</text>
        <view class="card-actions">
          <view class="card-action-meta">
            <text v-if="card.is_default" class="default-label">{{ t('defaultBankCard') }}</text>
            <text v-else-if="isRegisteredStatus(card.status)" class="action-link" @tap="onDefault(card.id)">{{ t('setDefault') }}</text>
            <text class="manual-label">{{ t('bankNotVerifiedBadge') }}</text>
          </view>
          <text v-if="card.status !== 'disabled'" class="delete-link" @tap="onDelete(card.id)">{{ t('disableBankCard') }}</text>
        </view>
      </view>

      <view v-if="bindingEnabled && !showForm" class="btn-add" @tap="openForm">+ {{ t('addBankCard') }}</view>

      <view v-if="showForm" class="card form-card">
        <view class="form-head">
          <text class="form-title">{{ t('addBankCard') }}</text>
          <text class="form-close" @tap="showForm = false">{{ t('cancel') }}</text>
        </view>

        <view class="field">
          <text class="field-label">{{ t('cardholder') }}</text>
          <view class="readonly-input">{{ form.holder || t('identityNameUnavailable') }}</view>
          <text class="field-hint">{{ t('cardholderMustMatchIdentity') }}</text>
        </view>
        <view class="field">
          <text class="field-label">{{ t('bankCardNumber') }}</text>
          <input class="field-input" v-model="form.card_number" type="number" maxlength="19" :placeholder="t('enterDebitCardNumber')" placeholder-class="placeholder" @input="onCardInput" />
          <text v-if="detectedBank" class="detected-bank">{{ t('detectedBankValue', { bank: tr(detectedBank) }) }}</text>
        </view>
        <view class="field">
          <text class="field-label">{{ t('bankName') }}</text>
          <input class="field-input" v-model="form.bank_name" :placeholder="t('bankNamePlaceholder')" placeholder-class="placeholder" />
        </view>
        <view class="field">
          <text class="field-label">{{ t('reservedPhone') }}</text>
          <input class="field-input" v-model="form.phone" type="number" maxlength="11" :placeholder="t('enterReservedPhone')" placeholder-class="placeholder" />
        </view>

        <view class="consent-row" @tap="consent = !consent">
          <view class="check-box" :class="{ checked: consent }">{{ consent ? '✓' : '' }}</view>
          <text class="consent-text">{{ t('bankCardConsent') }}</text>
        </view>
        <view class="risk-note">{{ t('manualBankCardSecurityHint') }}</view>
        <view class="submit-button" :class="{ disabled: submitting || !consent }" @tap="onAdd">{{ t(submitting ? 'submitting' : 'registerBankCard') }}</view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { addBankCard, deleteCard, getBankCardConfig, getBankCards, setDefaultCard, type BankCardItem } from '@/api/bank-card'
import { getVerification, type VerificationInfo } from '@/api/verification'
import AppNavBar from '@/components/AppNavBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useI18nStore } from '@/store/i18n'
import { bankNameSuggestion, isRegisteredBankCardStatus, luhnCheckCardNumber } from '@/utils/bank-card'
import { navigateTo as nav } from '@/utils/nav'

const i18n = useI18nStore()
const { t, tr } = i18n
const list = ref<BankCardItem[]>([])
const verification = ref<VerificationInfo | null>(null)
const loading = ref(true)
const loadError = ref(false)
const bindingEnabled = ref(false)
const showForm = ref(false)
const submitting = ref(false)
const detectedBank = ref('')
const consent = ref(false)
const form = reactive({ bank_name: '', card_number: '', holder: '', phone: '' })

function bankCardStatusLabel(status: BankCardItem['status']) {
  return ({ registered: 'bankCardStatusRegistered', pending_review: 'bankCardStatusRegistered', active: 'bankCardStatusRegistered', rejected: 'bankCardStatusRejected', disabled: 'bankCardStatusDisabled' })[status]
}
function cardStatusTone(status: BankCardItem['status']) {
  return isRegisteredStatus(status) ? 'registered' : status === 'rejected' ? 'danger' : 'muted'
}
function isRegisteredStatus(status: BankCardItem['status']) {
  return isRegisteredBankCardStatus(status)
}
function onCardInput() {
  form.card_number = form.card_number.replace(/\D/g, '').slice(0, 19)
  const previousSuggestion = detectedBank.value
  const nextSuggestion = bankNameSuggestion(form.card_number)
  if (previousSuggestion && form.bank_name === previousSuggestion) form.bank_name = nextSuggestion
  else if (nextSuggestion && !form.bank_name.trim()) form.bank_name = nextSuggestion
  detectedBank.value = nextSuggestion
}
function openForm() {
  form.holder = verification.value?.real_name || ''
  showForm.value = true
}
async function load() {
  loading.value = true
  loadError.value = false
  const [cardsResult, configResult, verificationResult] = await Promise.allSettled([getBankCards(), getBankCardConfig(), getVerification()])
  if (cardsResult.status === 'fulfilled') list.value = cardsResult.value
  else loadError.value = true
  if (configResult.status === 'fulfilled') {
    bindingEnabled.value = configResult.value.binding_enabled
  }
  if (verificationResult.status === 'fulfilled') {
    verification.value = verificationResult.value
    form.holder = verificationResult.value.real_name || ''
  }
  loading.value = false
}
onShow(() => { void load() })
async function onAdd() {
  if (submitting.value || !consent.value) return
  if (!bindingEnabled.value) return uni.showToast({ title: t('bankCardBindingUnavailable'), icon: 'none' })
  if (!form.holder) return uni.showToast({ title: t('completeIdentityFirst'), icon: 'none' })
  if (!/^\d{12,19}$/.test(form.card_number)) return uni.showToast({ title: t('enterValidBankCard'), icon: 'none' })
  if (!luhnCheckCardNumber(form.card_number)) return uni.showToast({ title: t('bankCardLuhnFailed'), icon: 'none' })
  if (!form.bank_name.trim()) return uni.showToast({ title: t('enterBankName'), icon: 'none' })
  if (!/^1\d{10}$/.test(form.phone)) return uni.showToast({ title: t('enterValidReservedPhone'), icon: 'none' })
  submitting.value = true
  try {
    await addBankCard({ ...form, is_default: list.value.length === 0 })
    uni.showToast({ title: t('bankCardRegistered'), icon: 'success' })
    showForm.value = false
    form.bank_name = ''; form.card_number = ''; form.phone = ''; detectedBank.value = ''; consent.value = false
    await load()
  } finally { submitting.value = false }
}
async function onDefault(id: number) { try { await setDefaultCard(id); await load() } catch {} }
function onDelete(id: number) {
  uni.showModal({ title: t('disableBankCard'), content: t('disableBankCardConfirm'), success: async result => {
    if (result.confirm) { try { await deleteCard(id); await load() } catch {} }
  } })
}
function goVerification() { nav('/pages/verification/index') }
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.shell { flex: 1; padding: 24rpx 32rpx calc(132rpx + var(--safe-bottom)); box-sizing: border-box; }
.card, .notice-card, .verify-card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); }
.notice-card { padding: 26rpx 28rpx; margin-bottom: 18rpx; border-color: rgba(24,175,196,.24); background: var(--primary-soft); }
.notice-title { display: block; color: var(--text); font-size: 28rpx; font-weight: 750; }
.notice-text { display: block; color: var(--text-sub); font-size: 23rpx; line-height: 1.65; margin-top: 8rpx; }
.verify-card { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 22rpx 24rpx; margin-bottom: 18rpx; }
.verify-title { display: block; color: var(--text); font-size: 25rpx; font-weight: 700; }
.verify-text { display: block; color: var(--text-sub); font-size: 21rpx; line-height: 1.5; margin-top: 5rpx; }
.verify-link { flex: none; color: var(--primary); font-size: 24rpx; font-weight: 700; padding: 16rpx 0; }
.service-warning { padding: 22rpx 24rpx; margin-bottom: 18rpx; color: var(--down); background: var(--down-soft); border: 1rpx solid rgba(220,73,73,.18); border-radius: var(--radius); font-size: 23rpx; line-height: 1.55; }
.state { color: var(--text-sub); text-align: center; padding: 72rpx 0; font-size: 25rpx; }
.load-error { display: flex; justify-content: space-between; align-items: center; gap: 20rpx; color: var(--text-sub); padding: 24rpx; background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 23rpx; }
.load-retry { color: var(--primary); font-weight: 700; padding: 18rpx 0; }
.empty-card { padding: 70rpx 0; margin-bottom: 18rpx; }
.bank-card { padding: 28rpx; margin-bottom: 16rpx; }
.bank-card.status-registered, .bank-card.status-active, .bank-card.status-pending_review { border-color: rgba(24,175,196,.24); }
.card-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 20rpx; }
.bank-name { display: block; color: var(--text); font-size: 29rpx; font-weight: 750; }
.card-number { display: block; color: var(--text-sub); font-size: 27rpx; font-variant-numeric: tabular-nums; letter-spacing: 1rpx; margin-top: 8rpx; }
.status-badge { flex: none; padding: 7rpx 14rpx; border-radius: 999rpx; font-size: 20rpx; font-weight: 700; }
.status-badge.registered { color: var(--primary); background: var(--primary-soft); }
.status-badge.danger { color: var(--down); background: var(--down-soft); }
.status-badge.muted { color: var(--text-dim); background: var(--bg-2); }
.card-meta { display: flex; flex-direction: column; gap: 7rpx; color: var(--text-sub); font-size: 22rpx; margin-top: 22rpx; }
.reject-reason { display: block; color: var(--down); background: var(--down-soft); border-radius: 12rpx; padding: 14rpx 16rpx; margin-top: 16rpx; font-size: 22rpx; line-height: 1.45; }
.card-actions { display: flex; justify-content: space-between; align-items: center; gap: 18rpx; border-top: 1rpx solid var(--divider); margin-top: 22rpx; padding-top: 18rpx; min-height: 52rpx; }
.card-action-meta { min-width: 0; display: flex; align-items: center; flex-wrap: wrap; gap: 12rpx; }
.default-label, .action-link { color: var(--primary); font-size: 23rpx; font-weight: 700; }
.manual-label { color: var(--text-dim); font-size: 21rpx; }
.delete-link { color: var(--down); font-size: 23rpx; padding: 10rpx 0; }
.btn-add { min-height: 86rpx; display: flex; align-items: center; justify-content: center; color: var(--primary); border: 1rpx dashed var(--primary); border-radius: var(--radius); font-size: 27rpx; font-weight: 700; margin: 22rpx 0; }
.form-card { padding: 28rpx; margin-top: 20rpx; }
.form-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 28rpx; }
.form-title { color: var(--text); font-size: 31rpx; font-weight: 750; }
.form-close { color: var(--text-sub); font-size: 24rpx; padding: 12rpx 0; }
.field { margin-bottom: 28rpx; }
.field-label { display: block; color: var(--text-sub); font-size: 23rpx; margin-bottom: 11rpx; }
.field-input, .readonly-input { min-height: 82rpx; display: flex; align-items: center; color: var(--text); background: var(--input-bg); border-radius: 16rpx; padding: 0 22rpx; font-size: 28rpx; box-sizing: border-box; }
.readonly-input { color: var(--text-sub); }
.placeholder { color: var(--text-dim); font-size: 25rpx; }
.field-hint, .detected-bank { display: block; color: var(--text-dim); font-size: 20rpx; line-height: 1.45; margin-top: 8rpx; }
.detected-bank { color: var(--primary); }
.consent-row { display: flex; align-items: flex-start; gap: 14rpx; padding: 12rpx 0; }
.check-box { flex: none; width: 34rpx; height: 34rpx; border: 1rpx solid var(--border); border-radius: 8rpx; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 22rpx; }
.check-box.checked { background: var(--primary); border-color: var(--primary); }
.consent-text { color: var(--text-sub); font-size: 22rpx; line-height: 1.55; }
.risk-note { color: var(--text-sub); background: var(--bg-2); border-radius: 14rpx; padding: 18rpx; margin-top: 12rpx; font-size: 21rpx; line-height: 1.55; }
.submit-button { min-height: 88rpx; display: flex; align-items: center; justify-content: center; background: var(--primary); color: #fff; border-radius: var(--radius); font-size: 28rpx; font-weight: 750; margin-top: 24rpx; }
.submit-button.disabled { opacity: .42; }
</style>
