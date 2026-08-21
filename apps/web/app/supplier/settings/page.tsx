import type { Metadata } from "next";
import { MobileSupplierOperations } from "@/components/mobile-supplier-operations";
import { ProductShell } from "@/components/product-shell";

export const metadata: Metadata = { title: "商家设置" };
export default function SupplierSettingsPage() { return <ProductShell variant="supplier"><MobileSupplierOperations section="settings" /></ProductShell>; }
