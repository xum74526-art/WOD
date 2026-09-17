import { AuthShell } from "@/components/auth-shell";
import type { Metadata } from "next";
import { localizedPageMetadata } from "@/lib/server/localized-metadata";

export function generateMetadata(): Promise<Metadata> {
  return localizedPageMetadata({
    "zh-Hant": {
      title: "重設密碼 | 算力星图",
      description: "使用安全連結為算力星图帳號設定新密碼。",
    },
    "zh-Hans": {
      title: "重置密码 | 算力星图",
      description: "使用安全链接为算力星图账号设置新密码。",
    },
    en: {
      title: "Reset password | 算力星图",
      description: "Use a secure link to set a new password for your 算力星图 account.",
    },
  }, { robots: { index: false, follow: false } });
}

export default function ResetPasswordPage() {
  return <AuthShell mode="reset" />;
}
