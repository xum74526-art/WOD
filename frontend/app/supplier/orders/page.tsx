import type { Metadata } from "next";
import { OrderWorkspace } from "@/components/order-workspace";
import { ProductShell } from "@/components/product-shell";

export const metadata: Metadata = { title: "订单记录" };

export default function SupplierOrdersPage() {
  return <ProductShell variant="supplier"><OrderWorkspace scope="supplier" /></ProductShell>;
}
