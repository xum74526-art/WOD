<template>
  <view class="withdraw-action" @tap="openWallet">{{ t('withdraw') }}</view>
</template>

<script setup lang="ts">
import { navigateTo as nav } from '@/utils/nav'
import { useI18nStore } from '@/store/i18n'

const { t } = useI18nStore()
function openWallet() { nav('/pages/wallet/index?withdraw=1') }
</script>

<style scoped>
.withdraw-action { flex: 1; min-height: 76rpx; display: flex; align-items: center; justify-content: center; color: #fff; background: var(--primary); border-radius: var(--radius); font-weight: 700; }
</style>
