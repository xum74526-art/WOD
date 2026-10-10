import type { Metadata } from "next";
import { AdminAuditLogWorkspace } from "@/components/admin-audit-log-workspace";

export const metadata: Metadata = { title: "操作审计" };

export default function AdminAuditPage() {
  return <AdminAuditLogWorkspace />;
}
