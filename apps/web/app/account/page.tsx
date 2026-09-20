import type { Metadata } from "next";
import { AccountDashboard } from "@/components/account-dashboard";

export const metadata: Metadata = { title: "個人工作臺" };

export default function AccountPage() {
  return <AccountDashboard />;
}
