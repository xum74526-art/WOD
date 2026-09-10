import type { Metadata } from "next";
import { AuthShell } from "@/components/auth-shell";
import { localizedPageMetadata } from "@/lib/server/localized-metadata";

export function generateMetadata(): Promise<Metadata> {
  return localizedPageMetadata({
    "zh-Hant": {
      title: "登入 | 北斗 kai",
      description: "登入北斗 kai，查看算力資源、訂單、資產及帳號資料。",
    },
    "zh-Hans": {
      title: "登录 | 北斗 kai",
      description: "登录北斗 kai，查看算力资源、订单、资产及账号资料。",
    },
    en: {
      title: "Sign in | KAI",
      description: "Sign in to KAI to access compute resources, orders, assets, and account settings.",
    },
  });
}

export default function LoginPage() {
  return <AuthShell mode="login" />;
}
