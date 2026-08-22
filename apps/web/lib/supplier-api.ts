import { apiRequest } from "@/lib/api";

export type MobileSupplierDevice = {
  id: number;
  name: string;
  gpu_model: string;
  memory: string;
  price: number;
  stock: number;
  region: string;
  city: string;
  order_count: number;
  status: "online" | "offline";
  list_status: "on" | "off";
  image_url: string | null;
};

export type MobileSupplierDashboard = {
  company_name: string;
  today_revenue: number;
  total_revenue: number;
  product_count: number;
  total_stock: number;
  pending_orders: number;
  completed_orders: number;
  devices: MobileSupplierDevice[];
  rating: number;
  order_count: number;
  trend: Array<{ date: string; amount: number }>;
};

export function getMobileSupplierDashboard() {
  return apiRequest<MobileSupplierDashboard>("/api/v1/mobile/supplier/dashboard");
}

export function listMobileSupplierDevices(statusFilter: "all" | "on" | "off" = "all") {
  return apiRequest<MobileSupplierDevice[]>(`/api/v1/mobile/supplier/devices?status_filter=${statusFilter}`);
}

export function createMobileSupplierDevice(input: Record<string, unknown>) {
  return apiRequest<MobileSupplierDevice>("/api/v1/mobile/supplier/devices", { method: "POST", body: JSON.stringify(input) });
}

export function updateMobileSupplierDevice(id: number, input: Record<string, unknown>) {
  return apiRequest<MobileSupplierDevice>(`/api/v1/mobile/supplier/devices/${id}`, { method: "PUT", body: JSON.stringify(input) });
}

export function deleteMobileSupplierDevice(id: number) {
  return apiRequest<{ id: number; deleted: boolean }>(`/api/v1/mobile/supplier/devices/${id}`, { method: "DELETE" });
}
