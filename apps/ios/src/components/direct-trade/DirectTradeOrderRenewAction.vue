<template>
  <view class="direct-renew">
    <view class="renew-button" @tap="openRenew">{{ t('renew') }}</view>
    <ConfirmSheet
      :visible="showRenew"
      :title="t('续费订单')"
      :desc="t('renewByHoursHint')"
      :cancelText="t('取消')"
      :confirmText="t('确认续费')"
      @cancel="cancelRenew"
      @confirm="submitRenewal"
    >
      <view class="cycles">
        <view
          v-for="value in RENEW_HOUR_OPTIONS"
          :key="value"
          class="cycle"
          :class="{ active: renewHours === value }"
          @tap="renewHours = value"
        >{{ t('hoursValue', { count: value }) }}</view>
      </view>
    </ConfirmSheet>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { renewOrder } from '@/api/order'
import ConfirmSheet from '@/components/ConfirmSheet.vue'
import { useI18nStore } from '@/store/i18n'

const props = defineProps<{ orderId: number }>()
const emit = defineEmits<{ refreshed: [] }>()
const { t } = useI18nStore()
const RENEW_HOUR_OPTIONS = [1, 6, 12, 24, 72, 168, 720]
const renewHours = ref(24)
const showRenew = ref(false)
const submitting = ref(false)
const pendingRequestId = ref('')
const pendingRequestKey = ref('')

function ensureRequestId(): string {
  const key = `${props.orderId}:${renewHours.value}`
  if (!pendingRequestId.value || pendingRequestKey.value !== key) {
    pendingRequestKey.value = key
    pendingRequestId.value = `renew-${props.orderId}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
  }
  return pendingRequestId.value
}

function openRenew() {
  ensureRequestId()
  showRenew.value = true
}

function cancelRenew() {
  showRenew.value = false
  pendingRequestId.value = ''
  pendingRequestKey.value = ''
}

async function submitRenewal() {
  showRenew.value = false
  if (submitting.value) return
  submitting.value = true
  try {
    await renewOrder(props.orderId, renewHours.value, ensureRequestId())
    pendingRequestId.value = ''
    pendingRequestKey.value = ''
    uni.showToast({ title: t('续费成功'), icon: 'success' })
    emit('refreshed')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.direct-renew { width: 100%; }
.renew-button { width: 100%; min-height: 76rpx; display: flex; align-items: center; justify-content: center; color: #fff; background: var(--primary); border-radius: var(--radius); font-size: 28rpx; font-weight: 700; }
.cycles { display: flex; flex-wrap: wrap; gap: 16rpx; }
.cycle { padding: 18rpx 24rpx; color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: 16rpx; }
.cycle.active { color: var(--primary); border-color: var(--primary); background: var(--primary-soft); }
</style>
