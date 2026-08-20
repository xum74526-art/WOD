import type { Metadata } from "next";
import { NotificationWorkspace } from "@/components/notification-workspace";

export const metadata: Metadata = { title: "通知中心" };
export default function NotificationsPage() { return <NotificationWorkspace />; }
