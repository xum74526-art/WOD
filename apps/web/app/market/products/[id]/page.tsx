import { ProductDetail } from "@/components/product-detail";
import { SiteHeader } from "@/components/site-header";

export default async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <div className="site-page"><SiteHeader /><main className="public-data-page"><ProductDetail productId={id} /></main></div>;
}
