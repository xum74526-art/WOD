export const QIXIANGPAY_REFERER = 'https://api.payqixiang.cn'
export const QIXIANGPAY_RETURN_URL = 'https://wod.kai.com/payment/qixiang/return'
export const PAYMENT_APP_URL_MATCH = '^(alipays|alipay|weixin)://.*'
export const PAYMENT_CHECKOUT_INTERCEPT_MATCH = '^(?:(?:alipays?|weixin)://.*|https://wod\\.kai\\.com/payment/qixiang/return(?:[?#][^\\s]*)?)$'

export type PaymentCheckoutFailureCode =
  | 'invalid-checkout-url'
  | 'checkout-open-failed'
  | 'payment-app-open-failed'

export interface PaymentCheckoutFailure {
  code: PaymentCheckoutFailureCode
  message: string
  cause?: unknown
}

export type PaymentCheckoutFailureHandler = (failure: PaymentCheckoutFailure) => void
export type PaymentCheckoutReturnHandler = () => void

/** Opening the wallet app can fail after checkout has already loaded. */
export function paymentCheckoutFailureCopy(failure: PaymentCheckoutFailure) {
  return failure.code === 'payment-app-open-failed'
    ? { title: 'paymentAppUnavailableTitle', message: 'paymentAppUnavailable' }
    : { title: 'paymentPageOpenFailedTitle', message: 'paymentPageOpenFailed' }
}

interface PaymentUrlLoadingEvent {
  url?: unknown
}

interface NativePaymentWebviewStyles {
  background: string
  cachemode: 'noCache'
  backButtonAutoControl: 'close'
  popGesture: 'close'
  disablePlus: true
  plusrequire: 'none'
  'uni-app': 'none'
  additionalHttpHeaders: Record<string, string>
}

interface NativePaymentWebview {
  overrideUrlLoading(
    options: {
      effect: 'instant'
      mode: 'reject'
      match: string
      exclude: 'none'
    },
    callback: (event: unknown) => void,
  ): void
  loadURL(url: string, additionalHttpHeaders?: Record<string, string>): void
  show(animation?: string): void
  close(animation?: string): void
}

export interface NativePaymentRuntime {
  runtime: {
    openURL(url: string, onError?: (error: unknown) => void): void
  }
  webview: {
    create(
      url: string,
      id: string,
      styles: NativePaymentWebviewStyles,
    ): NativePaymentWebview
  }
}

export interface BrowserLocationTarget {
  assign(url: string): void
}

let checkoutWebviewSequence = 0

function nextCheckoutWebviewId(): string {
  checkoutWebviewSequence += 1
  return `kai-qixiang-checkout-${Date.now()}-${checkoutWebviewSequence}`
}

function checkoutFailureMessage(error: unknown, fallback: string): string {
  if (!error || typeof error !== 'object') return fallback
  const message = (error as { message?: unknown }).message
  return typeof message === 'string' && message.trim() ? message.trim() : fallback
}

function reportFailure(
  onError: PaymentCheckoutFailureHandler | undefined,
  code: PaymentCheckoutFailureCode,
  message: string,
  cause?: unknown,
): void {
  onError?.({ code, message, cause })
}

/**
 * Validate without the browser URL global: the native App JS engine does not
 * provide it consistently. The backend supplies the trusted checkout target;
 * this boundary only permits an HTTPS navigation.
 */
export function normalizePaymentCheckoutUrl(value: string): string {
  const target = String(value || '').trim()
  if (!/^https:\/\/[^\s]+$/i.test(target)) return ''
  return target
}

export function isPaymentAppUrl(value: unknown): value is string {
  return typeof value === 'string' && /^(?:alipays?|weixin):\/\//i.test(value.trim())
}

export function isPaymentReturnUrl(value: unknown): value is string {
  return typeof value === 'string'
    && value === value.trim()
    && /^https:\/\/wod\.kai\.com\/payment\/qixiang\/return(?:[?#][^\s]*)?$/.test(value)
}

function interceptedPaymentUrl(event: unknown): string {
  if (!event || typeof event !== 'object') return ''
  const candidate = (event as PaymentUrlLoadingEvent).url
  return isPaymentAppUrl(candidate) ? candidate.trim() : ''
}

/**
 * Open Qixiang Pay inside a restricted native WebView. Payment-app schemes are
 * rejected by the WebView first and handed to the operating system explicitly,
 * so an unavailable Alipay/WeChat handler cannot become a WebView error page.
 */
export function openNativePaymentCheckout(
  runtime: NativePaymentRuntime,
  value: string,
  onError?: PaymentCheckoutFailureHandler,
  onReturn?: PaymentCheckoutReturnHandler,
): boolean {
  const target = normalizePaymentCheckoutUrl(value)
  if (!target) {
    reportFailure(onError, 'invalid-checkout-url', '支付链接无效')
    return false
  }

  const headers = { Referer: QIXIANGPAY_REFERER }
  try {
    const checkout = runtime.webview.create('', nextCheckoutWebviewId(), {
      background: '#FFFFFF',
      cachemode: 'noCache',
      backButtonAutoControl: 'close',
      popGesture: 'close',
      disablePlus: true,
      plusrequire: 'none',
      'uni-app': 'none',
      additionalHttpHeaders: headers,
    })

    let returnHandled = false
    checkout.overrideUrlLoading({
      effect: 'instant',
      mode: 'reject',
      match: PAYMENT_CHECKOUT_INTERCEPT_MATCH,
      exclude: 'none',
    }, (event: unknown) => {
      const eventUrl = event && typeof event === 'object'
        ? (event as PaymentUrlLoadingEvent).url
        : undefined
      if (isPaymentReturnUrl(eventUrl)) {
        if (returnHandled) return
        returnHandled = true
        try { checkout.close('none') } catch {}
        try { onReturn?.() } catch {}
        return
      }
      const paymentUrl = interceptedPaymentUrl(event)
      if (!paymentUrl) return
      const handleOpenError = (error: unknown) => {
        reportFailure(
          onError,
          'payment-app-open-failed',
          checkoutFailureMessage(error, '未能打开所选支付应用'),
          error,
        )
      }
      try {
        runtime.runtime.openURL(paymentUrl, handleOpenError)
      } catch (error) {
        handleOpenError(error)
      }
    })

    checkout.loadURL(target, headers)
    checkout.show('pop-in')
    return true
  } catch (error) {
    reportFailure(
      onError,
      'checkout-open-failed',
      checkoutFailureMessage(error, '未能打开支付页面'),
      error,
    )
    return false
  }
}

export function openH5PaymentCheckout(
  location: BrowserLocationTarget,
  value: string,
  onError?: PaymentCheckoutFailureHandler,
): boolean {
  const target = normalizePaymentCheckoutUrl(value)
  if (!target) {
    reportFailure(onError, 'invalid-checkout-url', '支付链接无效')
    return false
  }
  try {
    location.assign(target)
    return true
  } catch (error) {
    reportFailure(
      onError,
      'checkout-open-failed',
      checkoutFailureMessage(error, '未能打开支付页面'),
      error,
    )
    return false
  }
}

export function openPaymentCheckout(
  value: string,
  onError?: PaymentCheckoutFailureHandler,
  onReturn?: PaymentCheckoutReturnHandler,
): boolean {
  // #ifdef APP-PLUS
  return openNativePaymentCheckout(plus as unknown as NativePaymentRuntime, value, onError, onReturn)
  // #endif

  // #ifdef H5
  if (typeof window !== 'undefined') {
    return openH5PaymentCheckout(window.location, value, onError)
  }
  // #endif

  reportFailure(onError, 'checkout-open-failed', '当前环境无法打开支付页面')
  return false
}
