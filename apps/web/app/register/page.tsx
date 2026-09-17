import type { Metadata } from "next";
import { AuthShell } from "@/components/auth-shell";
import { localizedPageMetadata } from "@/lib/server/localized-metadata";

export function generateMetadata(): Promise<Metadata> {
  return localizedPageMetadata({
    "zh-Hant": {
      title: "註冊 | 算力星图",
      description: "建立算力星图帳號，統一使用 Web、iOS 與 Android。",
    },
    "zh-Hans": {
      title: "注册 | 算力星图",
      description: "创建算力星图账号，统一使用 Web、iOS 与 Android。",
    },
    en: {
      title: "Create account | 算力星图",
      description: "Create a 算力星图 account for Web, iOS, and Android.",
    },
  });
}

export default function RegisterPage() {
  return <AuthShell mode="register" />;
}
