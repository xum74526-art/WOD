import { request } from './request'

export interface OnboardingItem {
  id: number
  entity_type: 'personal' | 'company'
  contact: string
  phone: string
  device_model: string
  device_count: number
  location?: string
  remark?: string
  status: 'submitted' | 'contacted' | 'approved' | 'rejected' | string
  review_note?: string
  reviewed_at?: string
  updated_at?: string
  version?: number
  created_at?: string
}

export function getOnboardingMine() {
  return request<OnboardingItem[]>({ url: '/onboarding/mine' })
}
export function submitOnboarding(data: { entity_type: string; contact: string; phone: string; device_model: string; device_count: number; location: string; remark?: string }) {
  return request<OnboardingItem>({ url: '/onboarding', method: 'POST', data })
}
