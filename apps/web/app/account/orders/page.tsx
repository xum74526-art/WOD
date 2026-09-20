import type { Metadata } from "next";
import { OrderWorkspace } from "@/components/order-workspace";

export const metadata: Metadata = { title: "我的訂單" };

export default function AccountOrdersPage() {
  return <OrderWorkspace scope="account" />;
}
