import type { Metadata } from "next";
import { MobileBuyRequestWorkspace } from "@/components/mobile-buy-request-workspace";
export const metadata: Metadata = { title: "我的求购" };
export default function BuyerRequestsPage() { return <MobileBuyRequestWorkspace view="buyer" />; }
