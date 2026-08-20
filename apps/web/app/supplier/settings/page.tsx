import type { Metadata } from "next";
import { ProductShell } from "@/components/product-shell";
import { SupplierSettingsWorkspace } from "@/components/supplier-settings-workspace";

export const metadata: Metadata = { title: "商家设置" };
export default function SupplierSettingsPage() { return <ProductShell variant="supplier"><SupplierSettingsWorkspace /></ProductShell>; }
