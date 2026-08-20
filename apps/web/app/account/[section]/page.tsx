import { notFound } from "next/navigation";
import { WorkspaceFeaturePage } from "@/components/workspace-feature-page";
import { accountFeatures } from "@/lib/workspace-features";

export default async function AccountSectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  const feature = accountFeatures[section];
  if (!feature) notFound();
  return <WorkspaceFeaturePage feature={feature} />;
}
