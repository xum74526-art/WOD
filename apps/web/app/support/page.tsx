import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { MobileSupportWorkspace } from "@/components/mobile-support-workspace";
import { localizedPageMetadata } from "@/lib/server/localized-metadata";

export function generateMetadata(): Promise<Metadata> {
  return localizedPageMetadata({
    "zh-Hant": {
      title: "幫助與客服 | KAI星算",
      description: "KAI星算自助客服與帳號工單。",
    },
    "zh-Hans": {
      title: "帮助与客服 | KAI星算",
      description: "KAI星算自助客服与账号工单。",
    },
    en: {
      title: "KAI Star Help & Support",
      description: "KAI Star self-service support and account tickets.",
    },
  });
}

export default function SupportPage() {
  return <div className="site-page public-v2"><SiteHeader /><main className="public-data-page"><MobileSupportWorkspace /></main><SiteFooter /></div>;
}
