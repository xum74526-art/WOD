import { notFound } from "next/navigation";
import { ProductShell } from "@/components/product-shell";
import { WorkspaceFeaturePage } from "@/components/workspace-feature-page";
import { supplierFeatures } from "@/lib/workspace-features";

export default async function SupplierSectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  const feature = supplierFeatures[section];
  if (!feature) notFound();
  return <ProductShell variant="supplier"><WorkspaceFeaturePage feature={feature} /></ProductShell>;
}

