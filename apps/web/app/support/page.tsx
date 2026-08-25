import type { Metadata } from "next";
import { cookies } from "next/headers";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { MobileSupportWorkspace } from "@/components/mobile-support-workspace";

export async function generateMetadata(): Promise<Metadata> {
  const english = (await cookies()).get("kai.locale")?.value === "en";
  return {
    title: { absolute: english ? "KAI Help & Support" : "帮助与客服 | 北斗 kai" },
    description: english ? "KAI self-service support and account tickets." : "北斗 kai 自助客服与账户工单。",
  };
}

export default function SupportPage() {
  return <div className="site-page public-v2"><SiteHeader /><main className="public-data-page"><MobileSupportWorkspace /></main><SiteFooter /></div>;
}
