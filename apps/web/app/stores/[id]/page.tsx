import { notFound } from "next/navigation";
import { MobileStoreDetail } from "@/components/mobile-store-detail";
import { SiteHeader } from "@/components/site-header";

export default async function StorePage({ params }: { params: Promise<{ id: string }> }) {
  const id = Number((await params).id);
  if (!Number.isInteger(id) || id <= 0) notFound();
  return <div className="site-page"><SiteHeader/><main className="public-data-page"><MobileStoreDetail id={id}/></main></div>;
}
