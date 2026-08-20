import { request } from './request'
import { makeIdempotencyKey } from '@/utils/idempotency'

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
  created_at?: string
}

export function getOnboardingMine() {
  return request<Record<string, { available?: boolean }>>({ url: '/account/modules' })
    .then(() => [] as OnboardingItem[])
}
export function submitOnboarding(data: { entity_type: string; contact: string; phone: string; device_model: string; device_count: number; location: string; remark?: string }) {
  return request<OnboardingItem>({
    url: '/hosted-devices',
    method: 'POST',
    headers: { 'Idempotency-Key': makeIdempotencyKey('hosted-device') },
    data: {
      name: `${data.contact}-${data.device_model}`,
      device_type: 'gpu_server',
      region: data.location || undefined,
      notes: `${data.entity_type}; ${data.phone}; 数量 ${data.device_count}; ${data.remark || ''}`,
    },
  })
}
