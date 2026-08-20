import type { Metadata } from "next";
import { AdminWithdrawalWorkspace } from "@/components/admin-withdrawal-workspace";

export const metadata: Metadata = { title: "商家提现结算" };
export default function AdminWithdrawalsPage() { return <AdminWithdrawalWorkspace />; }
