import type { Metadata } from "next";
import { BuyerRequests } from "@/components/buyer-requests";
export const metadata: Metadata = { title: "我的求购" };
export default function BuyerRequestsPage() { return <BuyerRequests />; }
