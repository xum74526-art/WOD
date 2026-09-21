/**
 * App motion tokens and native route animation helpers.
 *
 * Keep the motion language small and predictable: route changes use the
 * platform animation, while component feedback is handled by CSS transforms
 * and opacity. No business or data state belongs in this module.
 */

export type RouteMotion = 'push' | 'fade' | 'sheet' | 'none'

export const APP_MOTION = {
  routeIn: 240,
  routeOut: 220,
  tab: 180,
  micro: 160,
  sheet: 260,
  reduced: 80,
  lock: 420,
} as const

export function prefersReducedMotion(): boolean {
  try {
    return typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

export function navigateAnimation(motion: RouteMotion = 'push') {
  if (prefersReducedMotion() || motion === 'none') {
    return { animationType: 'none' as const, animationDuration: 0 }
  }
  if (motion === 'fade') {
    return { animationType: 'fade-in' as const, animationDuration: APP_MOTION.routeIn }
  }
  if (motion === 'sheet') {
    return { animationType: 'slide-in-bottom' as const, animationDuration: APP_MOTION.sheet }
  }
  return { animationType: 'pop-in' as const, animationDuration: APP_MOTION.routeIn }
}

export function backAnimation(motion: RouteMotion = 'push') {
  if (prefersReducedMotion() || motion === 'none') {
    return { animationType: 'none' as const, animationDuration: 0 }
  }
  if (motion === 'fade') {
    return { animationType: 'fade-out' as const, animationDuration: APP_MOTION.routeOut }
  }
  if (motion === 'sheet') {
    return { animationType: 'slide-out-bottom' as const, animationDuration: APP_MOTION.sheet }
  }
  return { animationType: 'pop-out' as const, animationDuration: APP_MOTION.routeOut }
}
