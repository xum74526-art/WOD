import { request } from './request'

export interface NotificationItem {
  id: number
  title: string
  content?: string
  title_en?: string
  content_en?: string
  type: string
  action_url?: string
  is_read: boolean
  created_at?: string
}

export type NotificationType = 'system' | 'order' | 'device' | 'revenue' | 'wallet'

export interface NotificationPreferences {
  order_enabled: boolean
  device_enabled: boolean
  revenue_enabled: boolean
  wallet_enabled: boolean
  system_enabled: boolean
  updated_at?: string
}

export interface NotificationDeliveryStatus {
  in_app_enabled: boolean
  system_push_configured: boolean
  system_push_provider?: string
  system_push_status: 'configured' | 'pending_configuration'
}

export interface NotificationPreferencesResponse {
  preferences: NotificationPreferences
  delivery: NotificationDeliveryStatus
}

export interface NotificationListResponse {
  items: NotificationItem[]
  unread: number
  total: number
  page: number
  page_size: number
  has_more: boolean
}

export function getNotifications(params?: {
  type_filter?: NotificationType
  unread_only?: boolean
  page?: number
  page_size?: number
}, silent = false) {
  return request<NotificationListResponse>({ url: '/notifications', data: params || {}, silent })
}

export function getUnreadCount(silent = true) {
  return request<{ unread: number }>({ url: '/notifications/unread-count', silent })
}

export function getNotificationPreferences(silent = false) {
  return request<NotificationPreferencesResponse>({ url: '/notifications/preferences', silent })
}

export function updateNotificationPreferences(data: Partial<NotificationPreferences>) {
  return request<NotificationPreferencesResponse>({
    url: '/notifications/preferences',
    method: 'PUT',
    data,
  })
}

export function markRead(id: number) {
  return request({ url: `/notifications/${id}/read`, method: 'POST' })
}

export function markAllRead() {
  return request({ url: '/notifications/read-all', method: 'POST' })
}
