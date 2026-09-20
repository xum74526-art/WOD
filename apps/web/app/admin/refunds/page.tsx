import type { Metadata } from "next";
import { AdminPaymentOperationsWorkspace } from "@/components/admin-payment-operations-workspace";

export const metadata: Metadata = { title: "充值與人民幣原路退款 · 管理控制檯" };

export default function AdminRefundsPage() { return <AdminPaymentOperationsWorkspace />; }
