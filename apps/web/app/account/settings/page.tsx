import type { Metadata } from "next";
import { MobileAccountSettings } from "@/components/mobile-account-settings";
import { localizedPageMetadata } from "@/lib/server/localized-metadata";

export function generateMetadata(): Promise<Metadata> {
  return localizedPageMetadata({
    "zh-Hant": {
      title: "帳號設定 | KAI星算",
      description: "管理帳號資料、密碼、綁定郵箱與 KAI 身份。",
    },
    "zh-Hans": {
      title: "账号设置 | KAI星算",
      description: "管理账号资料、密码、绑定邮箱与 KAI 身份。",
    },
    en: {
      title: "Account Settings | KAI Star",
      description: "Manage your profile, password, linked email, and KAI identity.",
    },
  });
}

export default function AccountSettingsPage() {
  return <MobileAccountSettings />;
}
