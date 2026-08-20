import type { Metadata } from "next";
import { AccountDashboard } from "@/components/account-dashboard";

export const metadata: Metadata = { title: "个人工作台" };

export default function AccountPage() {
  return <AccountDashboard />;
}
