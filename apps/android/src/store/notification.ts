import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getUnreadCount } from '@/api/notification'

const POLL_INTERVAL_MS = 30_000

export const useNotificationStore = defineStore('notification', () => {
  const unread = ref(0)
  const lastUpdatedAt = ref(0)
  let timer: ReturnType<typeof setInterval> | null = null
  let activeRequest: Promise<number> | null = null
  let generation = 0

  async function refresh(force = false) {
    if (!force && Date.now() - lastUpdatedAt.value < 10_000) return unread.value
    if (activeRequest) return activeRequest
    const requestGeneration = generation
    const requestPromise = getUnreadCount(true)
      .then((result) => {
        if (requestGeneration === generation) {
          unread.value = Math.max(0, Number(result.unread) || 0)
          lastUpdatedAt.value = Date.now()
        }
        return unread.value
      })
      .finally(() => {
        if (activeRequest === requestPromise) activeRequest = null
      })
    activeRequest = requestPromise
    return requestPromise
  }

  function setUnread(value: number) {
    unread.value = Math.max(0, Number(value) || 0)
    lastUpdatedAt.value = Date.now()
  }

  function startPolling() {
    stopPolling()
    refresh(true).catch(() => {})
    timer = setInterval(() => refresh(true).catch(() => {}), POLL_INTERVAL_MS)
  }

  function stopPolling() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  function reset() {
    generation += 1
    stopPolling()
    unread.value = 0
    lastUpdatedAt.value = 0
    activeRequest = null
  }

  return { unread, refresh, setUnread, startPolling, stopPolling, reset }
})
