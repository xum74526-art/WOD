import { request } from './request'

export interface InviteSummary {
  code: string
  invited_count: number
  qualified_count: number
  unverified_count: number
  total_reward: number
  pending_count: number
  rewarded_count: number
  current_tier: string
  next_tier_hint: string
  rewards_enabled: boolean
  reward_mode: 'disabled' | 'test_card_hours' | 'live'
}

export interface InviteRecordItem {
  id: number
  invitee_phone: string
  status: string // unverified / registered / ordered / rewarded
  reward_amount: number
  created_at?: string
  rewarded_at?: string | null
}

export function getInviteSummary() {
  return request<InviteSummary>({ url: '/invite/summary' })
}

export function getInviteRecords() {
  return request<{ total: number; items: InviteRecordItem[] }>({ url: '/invite/records' })
}
