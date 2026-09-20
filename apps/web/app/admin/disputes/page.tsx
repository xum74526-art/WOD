import type { Metadata } from "next";
import { AdminDisputeWorkspace } from "@/components/admin-dispute-workspace";

export const metadata: Metadata = { title: "訂單爭議仲裁" };
export default function AdminDisputesPage() { return <AdminDisputeWorkspace />; }
