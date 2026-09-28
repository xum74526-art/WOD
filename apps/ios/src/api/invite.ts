import { request } from './request'

export interface InviteRebateTier {
  min_qualified_count: number
  max_qualified_count: number | null
  rate_bps: number
}

export interface InviteSummary {
  code: string
  invited_count: number
  qualified_count: number
  unverified_count: number
  total_reward: number
  pending_reward?: number
  pending_count: number
  rewarded_count: number
  current_tier: string
  current_rate_bps?: number
  next_tier_hint: string
  rewards_enabled: boolean
  reward_mode: 'disabled' | 'test_card_hours' | 'live'
  program_code?: string
  policy_version?: string
  fixed_reward_card_hours?: number
  fixed_reward_total?: number
  fixed_reward_pending?: number
  commission_total?: number
  commission_pending?: number
  daily_limit?: number
  daily_used?: number
  daily_remaining?: number
  // Installed V1 clients and transitional servers use these aliases.
  daily_slots_used?: number
  daily_slots_remaining?: number
  next_reset_at?: string
  business_timezone?: string
  tiers?: InviteRebateTier[]
  eligible_friend_spend_card_hours?: number
  // Transitional server alias retained until all installed clients move to
  // eligible_friend_spend_card_hours.
  total_eligible_consumption_card_hours?: number
  rewards_withdrawable?: boolean
  rewards_transferable?: boolean
  qualification_requirement?: string
}

export interface InviteRecordItem {
  id: number
  invitee_phone?: string
  invitee_phone_masked?: string
  status?: string // Legacy alias: unverified / registered / ordered / rewarded
  legacy_status?: string
  reward_amount?: number
  created_at?: string
  rewarded_at?: string | null
  record_type?: string
  reward_type?: string
  qualification_status?: string
  qualification_reason?: string | null
  identity_verified_at?: string | null
  qualification_day?: string | null
  daily_slot?: number | null
  qualification_order_id?: number | null
  fixed_reward_status?: string
  fixed_reward_amount?: number
  qualified_at?: string | null
}

export interface InviteRecordsResponse {
  total: number
  page?: number
  page_size?: number
  items: InviteRecordItem[]
}

export interface InviteCommissionItem {
  id: number
  invitee_phone_masked?: string
  source_type: 'order' | 'renewal'
  order_id: number | null
  order_renewal_id: number | null
  base_card_hours: number
  rate_bps: number
  reward_card_hours: number
  status: 'pending' | 'settled' | 'forfeited'
  policy_version: string
  created_at?: string | null
  settled_at?: string | null
}

export interface InviteCommissionListResponse {
  total: number
  page: number
  page_size: number
  items: InviteCommissionItem[]
}

export function getInviteSummary() {
  return request<InviteSummary>({ url: '/invite/summary' })
}

export function getInviteRecords(page = 1, pageSize = 50) {
  return request<InviteRecordsResponse>({
    url: '/invite/records',
    data: { page, page_size: pageSize },
    silent: true,
  })
}

export function getInviteCommissions(page = 1, pageSize = 50) {
  return request<InviteCommissionListResponse>({
    url: '/invite/commissions',
    data: { page, page_size: pageSize },
    silent: true,
  })
}
