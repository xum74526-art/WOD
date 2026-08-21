import { notFound } from "next/navigation";
import { MobileSupplierOperations, type MobileSupplierSection } from "@/components/mobile-supplier-operations";
import { ProductShell } from "@/components/product-shell";
import { WorkspaceFeaturePage } from "@/components/workspace-feature-page";
import { supplierFeatures } from "@/lib/workspace-features";

const mobileSections = new Set<MobileSupplierSection>(["analytics", "rebates"]);

export default async function SupplierSectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  if (mobileSections.has(section as MobileSupplierSection)) {
    return <ProductShell variant="supplier"><MobileSupplierOperations section={section as MobileSupplierSection} /></ProductShell>;
  }
  const feature = supplierFeatures[section];
  if (!feature) notFound();
  return <ProductShell variant="supplier"><WorkspaceFeaturePage feature={feature} /></ProductShell>;
}
