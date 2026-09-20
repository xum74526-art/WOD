import type { Metadata } from "next";
import { AdminBankCardWorkspace } from "@/components/admin-bank-card-workspace";
export const metadata: Metadata = { title: "銀行卡登記複核" };
export default function AdminBankCardsPage() { return <AdminBankCardWorkspace />; }
