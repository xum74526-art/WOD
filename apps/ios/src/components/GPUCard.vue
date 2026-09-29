<template>
  <view class="gpu-card" @tap="onTap">
    <image class="gpu-img" :src="imageUrl" mode="aspectFill" @error="imageFailed = true" />
    <view class="gpu-body">
      <view class="gpu-head">
        <text class="gpu-name">{{ localizeProductName(product.name, i18n.lang) }}</text>
        <text class="gpu-tag">{{ product.memory }}</text>
      </view>
      <view class="gpu-price">
        <text class="price-label">{{ t(commerce.directTradeEnabled ? '国内参考价' : commerce.matchmakingEnabled && product.inquiry_available !== false ? 'servicePrice' : 'operationTemporarilyUnavailable') }}</text>
        <view v-if="commerce.directTradeEnabled" class="price-row">
          <text class="price">{{ formatCardHourCurrency(directTradeCardHoursPerGpuHour(product)) }}</text>
          <text class="unit">/h</text>
        </view>
        <view v-else-if="commerce.matchmakingEnabled && product.inquiry_available !== false" class="price-row">
          <text class="price">{{ t('inquiry') }}</text>
        </view>
        <view v-else class="price-row"><text class="price unavailable">{{ t('viewDetail') }}</text></view>
      </view>
      <view class="gpu-foot">
        <text class="cuda" v-if="product.cuda">CUDA {{ product.cuda }}</text>
        <text class="cuda" v-else>{{ t('算力商品') }}</text>
        <view v-if="commerce.directTradeEnabled" class="btn" :class="{ disabled: !directTradeProductPurchasable(product) }">{{ t(directTradeProductPurchasable(product) ? 'k_25575fc0' : 'viewDetail') }}</view>
        <view v-else-if="commerce.matchmakingEnabled && product.inquiry_available !== false" class="btn">{{ t('submitRequirement') }}</view>
        <view v-else class="btn disabled">{{ t('viewDetail') }}</view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Product } from '@/api/gpu'
import { formatCardHourCurrency } from '@/utils/format'
import { directTradeCardHoursPerGpuHour, directTradeProductPurchasable } from '@/utils/direct-trade'
import { fallbackProductImage, resolveProductImage } from '@/utils/product-image'
import { useI18nStore } from '@/store/i18n'
import { useCommerceStore } from '@/store/commerce'
import { localizeProductName } from '@/utils/localize-content'
const i18n = useI18nStore()
const { t } = i18n
const commerce = useCommerceStore()
const props = defineProps<{ product: Product }>()
const emit = defineEmits<{ (e: 'tap', p: Product): void }>()
const imageFailed = ref(false)
const imageUrl = computed(() => imageFailed.value
  ? fallbackProductImage(props.product.gpu_model)
  : resolveProductImage(props.product.image_url, props.product.gpu_model))
watch(() => props.product.id, () => { imageFailed.value = false })
function onTap() {
  emit('tap', props.product)
}
</script>

<style lang="scss" scoped>
.gpu-card {
  background: var(--card);
  border-radius: var(--radius);
  padding: 0;
  border: 1rpx solid var(--border);
  margin-bottom: 24rpx;
  overflow: hidden;
}
.gpu-img {
  width: 100%;
  height: 200rpx;
  background: var(--divider);
  display: block;
}
.gpu-body { padding: 28rpx 32rpx; }
.gpu-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20rpx;
}
.gpu-name {
  color: var(--text);
  font-size: 34rpx;
  font-weight: 600;
}
.gpu-tag {
  color: var(--primary);
  font-size: 24rpx;
  background: var(--primary-soft);
  padding: 6rpx 18rpx;
  border-radius: 10rpx;
}
.gpu-price { margin-bottom: 20rpx; }
.price-label { display: block; color: var(--text-sub); font-size: 22rpx; margin-bottom: 8rpx; }
.price-row { display: flex; align-items: baseline; }
.price { color: var(--up); font-size: 44rpx; font-weight: 700; font-variant-numeric: tabular-nums; }
.price.unavailable { color: var(--text-sub); font-size: 30rpx; }
.unit { color: var(--text-sub); font-size: 26rpx; margin-left: 8rpx; }
.gpu-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.cuda { color: var(--text-sub); font-size: 24rpx; }
.btn {
  color: var(--primary);
  font-size: 28rpx;
  border: 1rpx solid var(--primary);
  padding: 8rpx 28rpx;
  border-radius: 32rpx;
}
.btn.disabled { color: var(--text-dim); border-color: var(--border); }
</style>
