import type { Metadata } from "next";
import { AdminPlatformAuditWorkspace } from "@/components/admin-platform-audit-workspace";

export const metadata: Metadata = { title: "端口資料 · 管理控制檯" };
export default function AdminPlatformDataPage() { return <AdminPlatformAuditWorkspace />; }
