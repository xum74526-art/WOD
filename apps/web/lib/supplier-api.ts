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
  version: number;
};

export type MobileSupplierDeviceUpdate = {
  name?: string;
  price?: number;
  stock?: number;
  status?: "on" | "off";
};

export type MobileSupplierDeviceMutation = {
  id: number;
  name?: string;
  status?: "on" | "off";
  updated?: boolean;
  deleted?: boolean;
  version: number;
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
  return apiRequest<MobileSupplierDashboard>("/api/v1/canonical/supplier/dashboard");
}

export function listMobileSupplierDevices(statusFilter: "all" | "on" | "off" = "all") {
  return apiRequest<MobileSupplierDevice[]>(`/api/v1/canonical/supplier/devices?status_filter=${statusFilter}`);
}

export function createMobileSupplierDevice(input: Record<string, unknown>) {
  return apiRequest<MobileSupplierDeviceMutation>("/api/v1/canonical/supplier/devices", { method: "POST", body: JSON.stringify(input) });
}

export function updateMobileSupplierDevice(id: number, expectedVersion: number, input: MobileSupplierDeviceUpdate) {
  return apiRequest<MobileSupplierDeviceMutation>(`/api/v1/canonical/supplier/devices/${id}`, {
    method: "PUT",
    body: JSON.stringify({ ...input, expected_version: expectedVersion }),
  });
}

export function deleteMobileSupplierDevice(id: number, expectedVersion: number) {
  return apiRequest<MobileSupplierDeviceMutation>(
    `/api/v1/canonical/supplier/devices/${id}?expected_version=${expectedVersion}`,
    { method: "DELETE" },
  );
}
