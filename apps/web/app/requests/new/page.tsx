import type { Metadata } from "next";
import { SiteHeader } from "@/components/site-header";
import { BuyRequestForm } from "@/components/buy-request-form";

export const metadata: Metadata = { title: "发布求购" };
export default function NewRequestPage() { return <div className="site-page public-v2"><SiteHeader /><main className="public-data-page"><BuyRequestForm /></main></div>; }
