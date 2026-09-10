import type { Metadata } from "next";
import { AuthShell } from "@/components/auth-shell";
import { localizedPageMetadata } from "@/lib/server/localized-metadata";

export function generateMetadata(): Promise<Metadata> {
  return localizedPageMetadata({
    "zh-Hant": {
      title: "註冊 | 北斗 kai",
      description: "建立北斗 kai 帳號，統一使用 Web、iOS 與 Android。",
    },
    "zh-Hans": {
      title: "注册 | 北斗 kai",
      description: "创建北斗 kai 账号，统一使用 Web、iOS 与 Android。",
    },
    en: {
      title: "Create account | KAI",
      description: "Create a KAI account for Web, iOS, and Android.",
    },
  });
}

export default function RegisterPage() {
  return <AuthShell mode="register" />;
}
