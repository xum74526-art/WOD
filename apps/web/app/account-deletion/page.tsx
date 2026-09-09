import type { Metadata } from "next";
import { AccountDeletion } from "@/components/account-deletion";

export const metadata: Metadata = {
  title: "ZTW 账号注销",
  description: "申请注销 ZTW 账号、查看注销条件与数据处理说明。无需重新安装 App。",
  robots: { index: true, follow: true },
};

export default function AccountDeletionPage() {
  return <AccountDeletion />;
}
