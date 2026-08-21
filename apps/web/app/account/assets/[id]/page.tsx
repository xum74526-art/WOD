import { notFound } from "next/navigation";
import { MobileAssetDetail } from "@/components/mobile-asset-detail";

export default async function AssetDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const id = Number((await params).id);
  if (!Number.isInteger(id) || id <= 0) notFound();
  return <MobileAssetDetail id={id}/>;
}
