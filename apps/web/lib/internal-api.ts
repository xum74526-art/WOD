import { apiEnvelopeRequest, apiRequest } from "@/lib/api";
import { listOrders, type Order } from "@/lib/commerce-api";

export type Address = {
  id: number; label: string; recipient_name: string; phone: string; country_code: string;
  province: string; city: string; district: string | null; address_line: string;
  postal_code: string | null; is_default: boolean; created_at: string; updated_at: string; version: number;
};
export type Notice = {
  id: number; category: string; title: string; body: string; title_en: string | null; body_en: string | null; action_path: string | null;
  is_read: boolean; read_at: string | null; expires_at: string | null; created_at: string;
};
export type MajorAnnouncement = {
  id: number; title: string; content: string; title_en: string | null; content_en: string | null;
  action_url: string | null; created_at: string | null;
};
export type NotificationPreferences = {
  order_enabled: boolean; device_enabled: boolean; revenue_enabled: boolean;
  wallet_enabled: boolean; system_enabled: boolean; updated_at?: string;
};
export type NotificationPreferenceResponse = {
  preferences: NotificationPreferences;
  delivery: { in_app_enabled: boolean; system_push_configured: boolean; system_push_provider?: string; system_push_status: "configured" | "pending_configuration" };
};
export type Dispute = {
  id: number; dispute_no: string; order_id: number; status: string; reason: string; description: string;
  resolution: string | null; resolution_action: "release_to_supplier" | "refund_buyer" | null;
  created_at: string; updated_at: string; version: number;
};
export type SupplierProfile = {
  store_name: string; contact_name: string; contact_phone: string; service_regions: string[];
  introduction: string; created_at: string; updated_at: string; version: number;
};
export type SupplierSettingsSnapshot = {
  profile: SupplierProfile | null;
  application: { company_name: string; contact_name: string; contact_phone: string; region: string | null };
};

export function listAddresses() { return apiRequest<Address[]>("/api/v1/account/addresses"); }
export function createAddress(input: Record<string, unknown>) { return apiRequest<Address>("/api/v1/account/addresses", { method: "POST", body: JSON.stringify(input) }); }
export function updateAddress(id: number, input: Record<string, unknown>) { return apiRequest<Address>(`/api/v1/account/addresses/${id}`, { method: "PATCH", body: JSON.stringify(input) }); }
export function deleteAddress(id: number) { return apiRequest<{ deleted: boolean }>(`/api/v1/account/addresses/${id}`, { method: "DELETE" }); }
export function setDefaultAddress(id: number) { return apiRequest<Address>(`/api/v1/account/addresses/${id}/default`, { method: "POST" }); }

export function listNotifications(unreadOnly = false) { return apiEnvelopeRequest<Notice[]>(`/api/v1/notifications?unread_only=${unreadOnly}`); }
export function getMajorAnnouncement() { return apiRequest<MajorAnnouncement | null>("/api/v1/canonical/notifications/major-announcement"); }
export function getUnreadCount() { return apiRequest<{ unread_count: number }>("/api/v1/notifications/unread-count"); }
export function readNotification(id: number) { return apiRequest<Notice>(`/api/v1/notifications/${id}/read`, { method: "PATCH" }); }
export function readAllNotifications() { return apiRequest<{ updated_count: number }>("/api/v1/notifications/read-all", { method: "POST" }); }
export function deleteNotification(id: number) { return apiRequest<{ id: number; deleted: boolean }>(`/api/v1/notifications/${id}`, { method: "DELETE" }); }
export function getNotificationPreferences() { return apiRequest<NotificationPreferenceResponse>("/api/v1/canonical/notifications/preferences"); }
export function updateNotificationPreferences(input: Partial<NotificationPreferences>) { return apiRequest<NotificationPreferenceResponse>("/api/v1/canonical/notifications/preferences", { method: "PUT", body: JSON.stringify(input) }); }

export function listDisputes() { return apiRequest<Dispute[]>("/api/v1/account/disputes"); }
export function createDispute(input: { order_id: number; reason: string; description: string }) { return apiRequest<Dispute>("/api/v1/account/disputes", { method: "POST", body: JSON.stringify(input) }); }
export async function listDisputableOrders(): Promise<Order[]> {
  const result = await listOrders("account");
  return result.data.filter((order) => ["delivering", "completed", "running"].includes(order.status));
}

export function getSupplierSettings() { return apiRequest<SupplierSettingsSnapshot>("/api/v1/supplier/settings"); }
export function saveSupplierSettings(input: Record<string, unknown>) { return apiRequest<SupplierProfile>("/api/v1/supplier/settings", { method: "PUT", body: JSON.stringify(input) }); }
