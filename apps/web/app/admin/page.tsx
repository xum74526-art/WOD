import type { Metadata } from "next";
import { AdminDashboard } from "@/components/admin-dashboard";

export const metadata: Metadata = { title: "管理控制檯" };
export default function AdminPage() { return <AdminDashboard />; }
