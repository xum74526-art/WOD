import type { Metadata } from "next";
import { AdminNotificationWorkspace } from "@/components/admin-notification-workspace";

export const metadata: Metadata = { title: "消息发布 · 管理控制台" };

export default function AdminNotificationsPage() {
  return <AdminNotificationWorkspace />;
}
