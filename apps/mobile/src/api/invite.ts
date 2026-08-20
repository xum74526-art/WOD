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
  return request<any>({ url: '/account/referrals' }).then(result => ({
    code: result.referral_code || '',
    invited_count: result.relations?.length || 0,
    qualified_count: 0,
    unverified_count: result.relations?.length || 0,
    total_reward: 0,
    pending_count: 0,
    rewarded_count: result.rewards?.length || 0,
    current_tier: result.module?.available ? 'standard' : 'not_configured',
    next_tier_hint: result.module?.reason || '邀请奖励服务尚未配置',
    rewards_enabled: Boolean(result.module?.available),
    reward_mode: result.module?.available ? 'live' : 'disabled',
  } as InviteSummary))
}

export function getInviteRecords() {
  return request<any>({ url: '/account/referrals' }).then(result => {
    const items = (result.relations || []).map((row: any) => ({
      id: row.id,
      invitee_phone: row.invitee_phone || row.invitee || '',
      status: row.status || 'registered',
      reward_amount: Number(row.reward_amount || 0),
      created_at: row.created_at,
      rewarded_at: row.rewarded_at,
    }))
    return { total: items.length, items }
  })
}
