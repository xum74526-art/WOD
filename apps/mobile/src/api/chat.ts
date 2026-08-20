export type SupportMode = 'self_service' | 'ai_assisted'
export type SupportTicketStatus = 'pending_unassigned' | 'assigned' | 'resolved' | 'closed'

export interface SupportMessage {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  response_mode: SupportMode | 'user' | 'system'
  topic: string | null
  can_create_ticket: boolean
  reply_to_id: number | null
  created_at: string
}

export interface SupportTicket {
  id: number
  ticket_no: string
  conversation_id: number
  subject: string
  description: string
  category: string
  status: SupportTicketStatus
  assigned_to: string | null
  created_at: string
  updated_at: string
}

export interface SupportSession {
  conversation_id: number | null
  service_mode: SupportMode
  human_support_configured: boolean
  messages: SupportMessage[]
  tickets: SupportTicket[]
  notice: string
}

export interface SupportReply {
  conversation_id: number
  message: SupportMessage
  reply: string
  is_human: false
  service_mode: SupportMode
  can_create_ticket: boolean
}

export function getSupportSession(lang: 'zh' | 'en' = 'zh') {
  return Promise.resolve<SupportSession>({
    conversation_id: null,
    service_mode: 'self_service',
    human_support_configured: false,
    messages: [],
    tickets: [],
    notice: lang === 'en'
      ? 'Human support is not configured. Please use the help center.'
      : '人工客服尚未配置，请先使用帮助中心。',
  })
}

export function sendMessage(options: {
  message: string
  conversationId?: number | null
  clientMessageId: string
  lang?: 'zh' | 'en'
}) {
  const now = new Date().toISOString()
  const reply = options.lang === 'en'
    ? 'Human support is not configured yet. Your message was not uploaded.'
    : '人工客服尚未配置，本条消息未上传。'
  return Promise.resolve<SupportReply>({
    conversation_id: options.conversationId || 0,
    message: {
      id: Date.now(), role: 'user', content: options.message, response_mode: 'user',
      topic: null, can_create_ticket: false, reply_to_id: null, created_at: now,
    },
    reply,
    is_human: false,
    service_mode: 'self_service',
    can_create_ticket: false,
  })
}

export function createSupportTicket(options: {
  conversationId: number
  sourceMessageId?: number | null
  subject: string
  description: string
  category?: string | null
  lang?: 'zh' | 'en'
}) {
  return Promise.reject(new Error('人工工单服务尚未配置')) as Promise<{ ticket: SupportTicket; notice: string }>
}

export function listSupportTickets() {
  return Promise.resolve<{ items: SupportTicket[] }>({ items: [] })
}
