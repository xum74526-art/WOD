import { request, upload } from './request'
import { KAI_AUTH_APP_RETURN_URL } from '@/utils/kai-auth-callback'

export interface UserInfo {
  id: number
  username: string
  phone?: string | null
  phone_bound?: boolean
  avatar?: string
  role?: string
  supplier_status?: string
}

export function login(phone: string, password: string) {
  return request<{ token: string; user: UserInfo }>({
    url: '/auth/login', method: 'POST', data: { phone, password },
  })
}

export function register(username: string, phone: string, password: string, invite_code?: string, captcha_key?: string, captcha_code?: string) {
  return request<{ token: string; user: UserInfo }>({
    url: '/auth/register', method: 'POST', data: { username, phone, password, invite_code, captcha_key, captcha_code },
  })
}

export interface KaiAuthConfig {
  configured: boolean
  issuer: string
  scopes: string[]
  phone_binding_required: boolean
}

export function getKaiAuthConfig() {
  return request<KaiAuthConfig>({ url: '/auth/kai/config', silent: true })
}

export function startKaiAuth(intent: 'login' | 'register') {
  return request<{ authorization_url: string }>({
    url: '/auth/kai/start', method: 'POST', data: { intent, return_url: KAI_AUTH_APP_RETURN_URL },
  })
}

export function exchangeKaiTicket(ticket: string) {
  return request<{ token: string; user: UserInfo }>({
    url: '/auth/kai/exchange', method: 'POST', data: { ticket },
  })
}

export function getProfile() {
  return request<UserInfo>({ url: '/user/profile' })
}

export function updateProfile(data: { username?: string }) {
  return request<UserInfo>({ url: '/user/profile', method: 'PUT', data })
}

export function uploadAvatar(filePath: string) {
  return upload<{ avatar: string }>({
    url: '/user/avatar', filePath, name: 'avatar',
  })
}

export function changePassword(old_password: string, new_password: string) {
  return request({ url: '/user/password', method: 'POST', data: { old_password, new_password } })
}

export function switchRole() {
  return request<{ role: string }>({ url: '/user/role/switch', method: 'POST' })
}

export interface RebateSummary {
  month_spent: number
  month_rebated: number
  current_rate: number
  next_tier_hint: string
  pending_rebate: number
  rewards_enabled: boolean
  reward_mode: 'disabled' | 'test_card_hours' | 'live'
  monthly_cap: number
}

export function getRebateSummary() {
  return request<RebateSummary>({ url: '/user/rebate' })
}
