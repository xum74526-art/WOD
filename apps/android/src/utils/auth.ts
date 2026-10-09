import { clearPaymentAccountStorage } from './payment-account-storage'

const TOKEN_KEY = 'wod_token'
const USER_KEY = 'wod_user'

export function getToken(): string {
  return uni.getStorageSync(TOKEN_KEY) || ''
}

export function setToken(token: string): void {
  if (token !== getToken()) clearPaymentAccountStorage(uni)
  uni.setStorageSync(TOKEN_KEY, token)
}

export function clearAuth(): void {
  clearPaymentAccountStorage(uni)
  uni.removeStorageSync(TOKEN_KEY)
  uni.removeStorageSync(USER_KEY)
}
