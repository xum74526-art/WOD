import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { MobileSupportWorkspace } from "@/components/mobile-support-workspace";

export const metadata: Metadata = { title: "帮助与客服" };

export default function SupportPage() {
  return <div className="site-page"><SiteHeader /><main className="public-data-page"><MobileSupportWorkspace /></main><SiteFooter /></div>;
}
