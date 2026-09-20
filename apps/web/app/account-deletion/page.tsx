import type { Metadata } from "next";
import { AccountDeletion } from "@/components/account-deletion";

export const metadata: Metadata = {
  title: "算力星图帳號註銷",
  description: "申請註銷算力星图帳號、查看註銷條件與資料處理說明。無需重新安裝 App。",
  robots: { index: true, follow: true },
};

export default function AccountDeletionPage() {
  return <AccountDeletion />;
}
