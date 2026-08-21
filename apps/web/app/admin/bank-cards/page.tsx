import type { Metadata } from "next";
import { AdminBankCardWorkspace } from "@/components/admin-bank-card-workspace";
export const metadata: Metadata = { title: "银行卡登记复核" };
export default function AdminBankCardsPage() { return <AdminBankCardWorkspace />; }
