import { apiRequest } from "@/lib/api";
import { canonicalApiPath as path } from "@/lib/canonical-api";

export type SupportMessage = { id: number; role: "user" | "assistant" | "system"; content: string; response_mode: string; topic: string | null; can_create_ticket: boolean; reply_to_id: number | null; created_at: string };
export type SupportTicket = { id: number; ticket_no: string; conversation_id: number; subject: string; description: string; category: string; status: string; assigned_to: string | null; created_at: string; updated_at: string };
export type SupportSession = { conversation_id: number | null; service_mode: string; human_support_configured: boolean; messages: SupportMessage[]; tickets: SupportTicket[]; notice: string };
export function getSupportSession() { return apiRequest<SupportSession>(path("/chat/session?lang=zh")); }
export function sendSupportMessage(message: string, conversation_id?: number | null) { return apiRequest<{ conversation_id: number; message: SupportMessage; reply: string; can_create_ticket: boolean }>(path("/chat"), { method: "POST", body: JSON.stringify({ message, conversation_id: conversation_id || undefined, client_message_id: crypto.randomUUID(), lang: "zh" }) }); }
export function createSupportTicket(input: { conversation_id: number; source_message_id?: number; subject: string; description: string; category: string }) { return apiRequest<{ ticket: SupportTicket; notice: string }>(path("/chat/tickets"), { method: "POST", body: JSON.stringify({ ...input, lang: "zh" }) }); }
