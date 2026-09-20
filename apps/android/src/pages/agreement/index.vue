<template>
  <view class="page">
    <AppNavBar :title="document.title" />
    <scroll-view scroll-y class="body">
      <view class="content">
        <text class="h1">{{ document.title }}</text>

        <view class="metadata" :aria-label="document.title">
          <view v-for="item in document.metadata" :key="item.label" class="metadata-row">
            <text class="metadata-label">{{ item.label }}</text>
            <text class="metadata-value">{{ item.value }}</text>
          </view>
        </view>

        <view class="introduction">
          <text v-for="paragraph in document.introduction" :key="paragraph" class="p intro-p">{{ paragraph }}</text>
        </view>

        <view v-for="section in document.sections" :key="section.title" class="section">
          <text class="h2">{{ section.title }}</text>
          <text v-for="paragraph in section.paragraphs" :key="paragraph" class="p">{{ paragraph }}</text>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import AppNavBar from '@/components/AppNavBar.vue'
import { getLegalDocument, type LegalDocumentKind } from '@/config/legal-documents'
import { useI18nStore } from '@/store/i18n'

const i18n = useI18nStore()
const kind = ref<LegalDocumentKind>('agreement')
const document = computed(() => getLegalDocument(kind.value, i18n.lang))

onLoad((options) => {
  kind.value = options?.type === 'privacy' ? 'privacy' : 'agreement'
})
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.body { height: 100%; }
.content { padding: 32rpx; padding-bottom: calc(60rpx + var(--safe-bottom)); }
.h1 { display: block; margin: 8rpx 0 24rpx; color: var(--text); font-size: 38rpx; font-weight: 800; text-align: center; }
.metadata { padding: 22rpx 24rpx; border: 1rpx solid var(--card-border); border-radius: 18rpx; background: var(--card); }
.metadata-row { display: flex; gap: 18rpx; padding: 6rpx 0; align-items: flex-start; }
.metadata-label { flex: 0 0 150rpx; color: var(--text-dim); font-size: 22rpx; line-height: 1.55; }
.metadata-value { flex: 1; color: var(--text-sub); font-size: 22rpx; line-height: 1.55; word-break: break-word; }
.introduction { margin: 28rpx 0 8rpx; padding: 24rpx; border-left: 6rpx solid var(--primary); border-radius: 0 14rpx 14rpx 0; background: var(--primary-soft); }
.section { display: block; }
.h2 { display: block; margin: 34rpx 0 16rpx; color: var(--text); font-size: 30rpx; font-weight: 750; line-height: 1.45; }
.p { display: block; margin-bottom: 14rpx; color: var(--text-sub); font-size: 25rpx; line-height: 1.82; text-align: justify; }
.intro-p:last-child, .p:last-child { margin-bottom: 0; }
</style>
