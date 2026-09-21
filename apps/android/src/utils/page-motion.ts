import { nextTick, onUnmounted, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { APP_MOTION, prefersReducedMotion } from './motion'

/** Replays a light enter transition when a root/tab page becomes visible. */
export function usePageMotion() {
  const pageMotionClass = ref('')
  let resetTimer: ReturnType<typeof setTimeout> | null = null

  function playPageMotion() {
    if (resetTimer) clearTimeout(resetTimer)
    if (prefersReducedMotion()) {
      pageMotionClass.value = ''
      return
    }
    pageMotionClass.value = ''
    void nextTick(() => {
      pageMotionClass.value = 'page-motion-enter'
      resetTimer = setTimeout(() => {
        pageMotionClass.value = ''
        resetTimer = null
      }, APP_MOTION.routeIn + 40)
    })
  }

  onShow(playPageMotion)
  onUnmounted(() => {
    if (resetTimer) clearTimeout(resetTimer)
  })

  return { pageMotionClass, playPageMotion }
}
