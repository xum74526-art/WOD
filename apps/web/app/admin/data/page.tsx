import type { Metadata } from "next";
import { AdminPlatformAuditWorkspace } from "@/components/admin-platform-audit-workspace";

export const metadata: Metadata = { title: "端口数据 · 管理控制台" };
export default function AdminPlatformDataPage() { return <AdminPlatformAuditWorkspace />; }
