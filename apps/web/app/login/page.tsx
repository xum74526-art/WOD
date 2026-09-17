import type { Metadata } from "next";
import { AuthShell } from "@/components/auth-shell";
import { localizedPageMetadata } from "@/lib/server/localized-metadata";

export function generateMetadata(): Promise<Metadata> {
  return localizedPageMetadata({
    "zh-Hant": {
      title: "登入 | 算力星图",
      description: "登入算力星图，查看算力資源、訂單、資產及帳號資料。",
    },
    "zh-Hans": {
      title: "登录 | 算力星图",
      description: "登录算力星图，查看算力资源、订单、资产及账号资料。",
    },
    en: {
      title: "Sign in | 算力星图",
      description: "Sign in to 算力星图 to access compute resources, orders, assets, and account settings.",
    },
  });
}

export default function LoginPage() {
  return <AuthShell mode="login" />;
}
