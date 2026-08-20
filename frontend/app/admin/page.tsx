import type { Metadata } from "next";
import { AdminDashboard } from "@/components/admin-dashboard";

export const metadata: Metadata = { title: "管理控制台" };
export default function AdminPage() { return <AdminDashboard />; }
