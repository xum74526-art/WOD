import type { Metadata } from "next";
import { MobileSupplierOperations } from "@/components/mobile-supplier-operations";
import { ProductShell } from "@/components/product-shell";

export const metadata: Metadata = { title: "收益与提现" };
export default function SupplierRevenuePage() { return <ProductShell variant="supplier"><MobileSupplierOperations section="revenue" /></ProductShell>; }
