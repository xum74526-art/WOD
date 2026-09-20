import type { Metadata } from "next";
import { AuthShell } from "@/components/auth-shell";
import { localizedPageMetadata } from "@/lib/server/localized-metadata";

export function generateMetadata(): Promise<Metadata> {
  return localizedPageMetadata({
    "zh-Hant": {
      title: "註冊 | KAI星算",
      description: "建立KAI星算帳號，統一使用 Web、iOS 與 Android。",
    },
    "zh-Hans": {
      title: "注册 | KAI星算",
      description: "创建KAI星算账号，统一使用 Web、iOS 与 Android。",
    },
    en: {
      title: "Create account | KAI星算",
      description: "Create a KAI星算 account for Web, iOS, and Android.",
    },
  });
}

export default function RegisterPage() {
  return <AuthShell mode="register" />;
}
