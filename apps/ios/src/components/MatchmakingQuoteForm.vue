<template>
  <view class="quote-form-fields">
    <view class="field two-col">
      <view class="half">
        <text class="field-label">{{ t('proposalUnitPrice') }}</text>
        <input :value="modelValue.unitPrice" type="digit" class="field-input" :placeholder="t('proposalUnitPricePlaceholder')" @input="update('unitPrice', inputValue($event))" />
      </view>
      <view class="half">
        <text class="field-label">{{ t('proposalTotalPrice') }}</text>
        <input :value="modelValue.totalPrice" type="digit" class="field-input" :placeholder="t('proposalTotalPricePlaceholder')" @input="update('totalPrice', inputValue($event))" />
      </view>
    </view>
    <view class="field two-col">
      <view class="half">
        <text class="field-label">{{ t('deliveryTimeHours') }}</text>
        <input :value="modelValue.deliveryHours" type="number" class="field-input" :placeholder="t('deliveryTimeHoursPlaceholder')" @input="update('deliveryHours', inputValue($event))" />
      </view>
      <view class="half">
        <text class="field-label">{{ t('proposalValidityHours') }}</text>
        <input :value="modelValue.validityHours" type="number" class="field-input" :placeholder="t('proposalValidityHoursPlaceholder')" @input="update('validityHours', inputValue($event))" />
      </view>
    </view>
    <view class="field">
      <text class="field-label">{{ t('proposalNote') }}</text>
      <textarea :value="modelValue.message" class="field-textarea short" :placeholder="t('proposalNotePlaceholder')" maxlength="500" @input="update('message', inputValue($event))" />
    </view>
    <view class="form-buttons">
      <view v-if="showCancel" class="cancel-action" @tap="$emit('cancel')">{{ t('cancel') }}</view>
      <view class="submit-action" :class="{ disabled: busy || !valid }" @tap="submit">{{ submitLabel }}</view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18nStore } from '@/store/i18n'

export interface MatchmakingQuoteFormValue {
  unitPrice: string
  totalPrice: string
  deliveryHours: string
  validityHours: string
  message: string
}

const props = withDefaults(defineProps<{
  modelValue: MatchmakingQuoteFormValue
  submitLabel: string
  busy?: boolean
  showCancel?: boolean
}>(), { busy: false, showCancel: true })

const emit = defineEmits<{
  'update:modelValue': [value: MatchmakingQuoteFormValue]
  submit: []
  cancel: []
}>()

const { t } = useI18nStore()
const valid = computed(() => Number(props.modelValue.totalPrice) > 0
  && Number(props.modelValue.deliveryHours) > 0
  && Number(props.modelValue.validityHours) > 0)

function inputValue(event: any) {
  return String(event?.detail?.value ?? '')
}

function update(key: keyof MatchmakingQuoteFormValue, value: string) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

function submit() {
  if (!props.busy && valid.value) emit('submit')
}
</script>

<style lang="scss" scoped>
.quote-form-fields { margin-top: 20rpx; }
.field { margin-bottom: 22rpx; }
.field.two-col { display: flex; gap: 16rpx; }
.half { flex: 1; min-width: 0; }
.field-label { display: block; margin-bottom: 9rpx; color: var(--text-sub); font-size: 20rpx; }
.field-input { box-sizing: border-box; width: 100%; height: 72rpx; padding: 0 18rpx; color: var(--text); background: var(--bg); border: 1rpx solid var(--border); border-radius: 12rpx; font-size: 23rpx; }
.field-textarea { box-sizing: border-box; width: 100%; height: 126rpx; padding: 16rpx 18rpx; color: var(--text); background: var(--bg); border: 1rpx solid var(--border); border-radius: 12rpx; font-size: 22rpx; line-height: 1.5; }
.form-buttons { display: flex; gap: 14rpx; }
.cancel-action, .submit-action { flex: 1; min-height: 66rpx; display: flex; align-items: center; justify-content: center; border-radius: 12rpx; font-size: 22rpx; font-weight: 700; }
.cancel-action { color: var(--text); background: var(--bg); border: 1rpx solid var(--border); }
.submit-action { color: #fff; background: var(--primary); }
.submit-action.disabled { opacity: .45; }
</style>
