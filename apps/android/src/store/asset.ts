import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as assetApi from '@/api/asset'
import type { AssetSummary } from '@/api/asset'

export const useAssetStore = defineStore('asset', () => {
  const summary = ref<AssetSummary | null>(null)
  const loading = ref(false)
  const lastUpdated = ref(0)
  let refreshGeneration = 0

  async function refresh() {
    if (loading.value) return summary.value
    const generation = refreshGeneration
    loading.value = true
    try {
      const nextSummary = await assetApi.getAssets()
      if (generation === refreshGeneration) {
        summary.value = nextSummary
        lastUpdated.value = Date.now()
      }
    } finally {
      if (generation === refreshGeneration) loading.value = false
    }
    return summary.value
  }

  function reset() {
    refreshGeneration += 1
    summary.value = null
    loading.value = false
    lastUpdated.value = 0
  }

  return { summary, loading, lastUpdated, refresh, reset }
})
