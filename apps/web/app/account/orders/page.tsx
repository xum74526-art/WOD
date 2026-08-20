import type { Metadata } from "next";
import { OrderWorkspace } from "@/components/order-workspace";

export const metadata: Metadata = { title: "我的订单" };

export default function AccountOrdersPage() {
  return <OrderWorkspace scope="account" />;
}
