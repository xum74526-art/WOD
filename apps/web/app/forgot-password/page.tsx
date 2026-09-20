import { AuthShell } from "@/components/auth-shell";
import type { Metadata } from "next";
import { localizedPageMetadata } from "@/lib/server/localized-metadata";

export function generateMetadata(): Promise<Metadata> {
  return localizedPageMetadata({
    "zh-Hant": {
      title: "找回密碼 | KAI星算",
      description: "透過已綁定郵箱或 KAI 身份找回KAI星算帳號。",
    },
    "zh-Hans": {
      title: "找回密码 | KAI星算",
      description: "通过已绑定邮箱或 KAI 身份找回KAI星算账号。",
    },
    en: {
      title: "Recover account | KAI星算",
      description: "Recover your KAI星算 account with a linked email or KAI identity.",
    },
  }, { robots: { index: false, follow: false } });
}

export default function ForgotPasswordPage() {
  return <AuthShell mode="forgot" />;
}
