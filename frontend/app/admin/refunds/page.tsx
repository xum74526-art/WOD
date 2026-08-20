import type { Metadata } from "next";
import { AdminRefundWorkspace } from "@/components/admin-refund-workspace";

export const metadata: Metadata = { title: "退款处理" };
export default function AdminRefundsPage() { return <AdminRefundWorkspace />; }
