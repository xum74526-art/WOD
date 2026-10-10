import type { Metadata } from "next";
import { AdminSupportWorkspace } from "@/components/admin-support-workspace";

export const metadata: Metadata = { title: "客服工单" };

export default function AdminSupportPage() {
  return <AdminSupportWorkspace />;
}
