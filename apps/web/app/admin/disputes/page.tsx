import type { Metadata } from "next";
import { AdminDisputeWorkspace } from "@/components/admin-dispute-workspace";

export const metadata: Metadata = { title: "订单争议仲裁" };
export default function AdminDisputesPage() { return <AdminDisputeWorkspace />; }
