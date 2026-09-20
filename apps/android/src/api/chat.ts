import { request } from './request'

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
  return request<SupportSession>({
    url: `/chat/session?lang=${lang}`,
    silent: true,
  })
}

export function sendMessage(options: {
  message: string
  conversationId?: number | null
  clientMessageId: string
  lang?: 'zh' | 'en'
}) {
  return request<SupportReply>({
    url: '/chat',
    method: 'POST',
    silent: true,
    data: {
      message: options.message,
      conversation_id: options.conversationId || undefined,
      client_message_id: options.clientMessageId,
      lang: options.lang || 'zh',
    },
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
  return request<{ ticket: SupportTicket; notice: string }>({
    url: '/chat/tickets',
    method: 'POST',
    silent: true,
    data: {
      conversation_id: options.conversationId,
      source_message_id: options.sourceMessageId || undefined,
      subject: options.subject,
      description: options.description,
      category: options.category || 'other',
      lang: options.lang || 'zh',
    },
  })
}

export function listSupportTickets() {
  return request<{ items: SupportTicket[] }>({
    url: '/chat/tickets',
    silent: true,
  })
}
