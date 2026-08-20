import type { Metadata } from "next";
import { ProductShell } from "@/components/product-shell";
import { SupplierRevenueWorkspace } from "@/components/supplier-revenue-workspace";

export const metadata: Metadata = { title: "收益与提现" };
export default function SupplierRevenuePage() { return <ProductShell variant="supplier"><SupplierRevenueWorkspace /></ProductShell>; }
