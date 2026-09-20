import { AuthShell } from "@/components/auth-shell";
import type { Metadata } from "next";
import { localizedPageMetadata } from "@/lib/server/localized-metadata";

export function generateMetadata(): Promise<Metadata> {
  return localizedPageMetadata({
    "zh-Hant": {
      title: "重設密碼 | KAI星算",
      description: "使用安全連結為KAI星算帳號設定新密碼。",
    },
    "zh-Hans": {
      title: "重置密码 | KAI星算",
      description: "使用安全链接为KAI星算账号设置新密码。",
    },
    en: {
      title: "Reset password | KAI星算",
      description: "Use a secure link to set a new password for your KAI星算 account.",
    },
  }, { robots: { index: false, follow: false } });
}

export default function ResetPasswordPage() {
  return <AuthShell mode="reset" />;
}
