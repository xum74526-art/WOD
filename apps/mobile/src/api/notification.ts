import { request, requestEnvelope } from './request'

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

interface CanonicalNotification {
  id: number
  category: string
  title: string
  body: string
  action_path?: string | null
  is_read: boolean
  created_at?: string
}

function toNotification(row: CanonicalNotification): NotificationItem {
  return {
    id: row.id,
    title: row.title,
    content: row.body,
    type: row.category,
    action_url: row.action_path || undefined,
    is_read: row.is_read,
    created_at: row.created_at,
  }
}

export function getNotifications(params?: {
  type_filter?: NotificationType
  unread_only?: boolean
  page?: number
  page_size?: number
}, silent = false) {
  const page = params?.page || 1
  const pageSize = params?.page_size || 20
  return requestEnvelope<CanonicalNotification[], { total?: number }>({
    url: '/notifications',
    data: {
      page,
      page_size: pageSize,
      ...(params?.type_filter ? { category: params.type_filter } : {}),
      ...(params?.unread_only != null ? { unread_only: params.unread_only } : {}),
    },
    silent,
  }).then(({ data, meta }) => {
    const total = Number(meta.total ?? data.length)
    const items = data.map(toNotification)
    return {
      items,
      unread: items.filter(item => !item.is_read).length,
      total,
      page,
      page_size: pageSize,
      has_more: page * pageSize < total,
    }
  })
}

export function getUnreadCount(silent = true) {
  return request<{ unread_count: number }>({ url: '/notifications/unread-count', silent })
    .then(result => ({ unread: result.unread_count }))
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
  return request({ url: `/notifications/${id}/read`, method: 'PATCH' })
}

export function markAllRead() {
  return request({ url: '/notifications/read-all', method: 'POST' })
}
