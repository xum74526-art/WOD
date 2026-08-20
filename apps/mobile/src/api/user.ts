import { request } from './request'

export interface UserInfo {
  id: number
  username: string
  phone?: string | null
  phone_bound?: boolean
  avatar?: string
  role?: string
  supplier_status?: string
}

interface CanonicalUser {
  id: number
  display_name: string
  email?: string | null
  phone?: string | null
  phone_verified?: boolean
  role?: string
}

interface TokenSession {
  access_token: string
  token_type: 'Bearer'
  expires_in: number
  user: CanonicalUser
}

function toUserInfo(user: CanonicalUser): UserInfo {
  return {
    id: user.id,
    username: user.display_name,
    phone: user.phone,
    phone_bound: Boolean(user.phone_verified),
    role: user.role,
  }
}

function toMobileSession(session: TokenSession) {
  return { token: session.access_token, user: toUserInfo(session.user) }
}

export function login(identifier: string, password: string) {
  return request<TokenSession>({
    url: '/auth/token', method: 'POST', data: { identifier, password },
  }).then(toMobileSession)
}

export function register(username: string, identifier: string, password: string, invite_code?: string, captcha_key?: string, captcha_code?: string) {
  return request<TokenSession>({
    url: '/auth/token/register', method: 'POST', data: {
      display_name: username,
      identifier,
      password,
    },
  }).then(toMobileSession)
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
    url: '/auth/kai/start', method: 'POST', data: { intent },
  })
}

export function exchangeKaiTicket(ticket: string) {
  return request<TokenSession>({
    url: '/auth/kai/exchange', method: 'POST', data: { ticket },
  }).then(toMobileSession)
}

export function getProfile() {
  return request<{ user: CanonicalUser }>({ url: '/auth/token/me' })
    .then(result => toUserInfo(result.user))
}

export function revokeSession() {
  return request<{ revoked: boolean }>({ url: '/auth/token/revoke', method: 'POST', silent: true })
}

export function updateProfile(data: { username?: string }) {
  if (!data.username) return getProfile()
  return request<CanonicalUser>({
    url: '/account/profile', method: 'PATCH', data: { display_name: data.username },
  }).then(toUserInfo)
}

export function uploadAvatar(filePath: string) {
  void filePath
  return Promise.reject<{ avatar: string }>(new Error('头像存储服务尚未配置'))
}

export function changePassword(old_password: string, new_password: string) {
  return request({
    url: '/account/security/password',
    method: 'POST',
    data: { current_password: old_password, new_password },
  })
}

export function switchRole() {
  return Promise.reject<{ role: string }>(new Error('账户角色由商家审核流程确定，不能直接切换'))
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

export function getRebateSummary(): Promise<RebateSummary> {
  return request<any>({ url: '/account/referrals' }).then(result => ({
    month_spent: 0,
    month_rebated: 0,
    current_rate: 0,
    next_tier_hint: result.module?.reason || '奖励服务尚未配置',
    pending_rebate: 0,
    rewards_enabled: Boolean(result.module?.available),
    reward_mode: result.module?.available ? 'live' : 'disabled',
    monthly_cap: 0,
  }))
}
