import type { Metadata } from "next";
import { AuthShell } from "@/components/auth-shell";
import { localizedPageMetadata } from "@/lib/server/localized-metadata";

export function generateMetadata(): Promise<Metadata> {
  return localizedPageMetadata({
    "zh-Hant": {
      title: "登入 | KAI星算",
      description: "登入KAI星算，查看算力資源、訂單、資產及帳號資料。",
    },
    "zh-Hans": {
      title: "登录 | KAI星算",
      description: "登录KAI星算，查看算力资源、订单、资产及账号资料。",
    },
    en: {
      title: "Sign in | KAI星算",
      description: "Sign in to KAI星算 to access compute resources, orders, assets, and account settings.",
    },
  });
}

export default function LoginPage() {
  return <AuthShell mode="login" />;
}
