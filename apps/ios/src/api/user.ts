import { request, upload } from './request'
import { KAI_AUTH_APP_RETURN_URL } from '@/utils/kai-auth-callback'
import { CLIENT_PLATFORM } from '@/utils/client-platform'

export interface UserInfo {
  id: number
  username: string
  phone?: string | null
  phone_bound?: boolean
  password_set?: boolean
  phone_login_enabled?: boolean
  phone_masked?: string | null
  avatar?: string
  role?: string
  supplier_status?: string
}

export interface PhoneLoginStatus {
  configured: boolean
  phone_masked: string | null
  phone_verified: boolean
  can_configure: boolean
  sms_verification_available: boolean
}

export function getPhoneLoginStatus(silent = true) {
  return request<PhoneLoginStatus>({ url: '/user/login-phone', silent })
}

export function configurePhoneLogin(phone: string, password: string) {
  return request<UserInfo>({
    url: '/user/login-phone',
    method: 'POST',
    data: { phone, password },
  })
}

export function login(phone: string, password: string) {
  return request<{ token: string; user: UserInfo }>({
    url: '/auth/login', method: 'POST', data: { phone, password, client_id: CLIENT_PLATFORM },
  })
}

export function register(username: string, phone: string, password: string, invite_code?: string, captcha_key?: string, captcha_code?: string) {
  return request<{ token: string; user: UserInfo }>({
    url: '/auth/register', method: 'POST', data: { username, phone, password, invite_code, captcha_key, captcha_code, client_id: CLIENT_PLATFORM },
  })
}

export function logoutCurrentSession() {
  return request<{ logged_out: boolean; session_revoked: boolean }>({
    url: '/auth/logout', method: 'POST', silent: true, unauthorized: 'reject',
  })
}

export interface KaiAuthConfig {
  configured: boolean
  issuer: string
  scopes: string[]
  phone_binding_required: boolean
  auto_provision_enabled: boolean
  phone_login_setup_enabled: boolean
  sms_verification_available: boolean
}

export function getKaiAuthConfig() {
  return request<KaiAuthConfig>({ url: '/auth/kai/config', silent: true })
}

export function startKaiAuth(intent: 'login' | 'register') {
  return request<{ authorization_url: string }>({
    url: '/auth/kai/start', method: 'POST', data: { intent, return_url: KAI_AUTH_APP_RETURN_URL, client_id: CLIENT_PLATFORM, terms_accepted: true },
  })
}

export function exchangeKaiTicket(ticket: string) {
  return request<{ token: string; user: UserInfo }>({
    url: '/auth/kai/exchange', method: 'POST', data: { ticket },
  })
}

export interface KaiBindingStatus {
  bound: boolean
  provider: 'kai' | null
  issuer: string | null
}

export function getKaiBindingStatus(silent = true) {
  return request<KaiBindingStatus>({ url: '/auth/kai/status', silent })
}

export function startKaiBinding() {
  return request<{ authorization_url: string }>({
    url: '/auth/kai/bind/start',
    method: 'POST',
    data: { return_url: KAI_AUTH_APP_RETURN_URL },
  })
}

export function exchangeKaiBindTicket(ticket: string) {
  return request<KaiBindingStatus & { user: UserInfo }>({
    url: '/auth/kai/bind/exchange',
    method: 'POST',
    data: { ticket },
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

export interface ConsumerRebateTier {
  max_month_spent: number | null
  rate: number
}

export interface RebateSummary {
  program_code: 'consumer_purchase_rebate'
  policy_version: string
  period_key: string
  month_spent: number
  month_rebated: number
  month_entitled: number
  current_rate: number
  minimum_order_amount: number
  tiers: ConsumerRebateTier[]
  next_tier_hint: string
  pending_rebate: number
  rewards_enabled: boolean
  reward_mode: 'disabled' | 'test_card_hours' | 'live'
  monthly_cap: number
  cap_used: number
  cap_remaining: number
}

export function getRebateSummary() {
  return request<RebateSummary>({ url: '/user/rebate' })
}
