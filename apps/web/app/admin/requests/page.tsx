import type { Metadata } from "next";
import { AdminBuyRequestWorkspace } from "@/components/admin-buy-request-workspace";

export const metadata: Metadata = { title: "需求管理 · 管理控制檯" };

export default function AdminBuyRequestsPage() {
  return <AdminBuyRequestWorkspace />;
}
