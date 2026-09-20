import { ProductShell } from "@/components/product-shell";
import { MobileBuyRequestWorkspace } from "@/components/mobile-buy-request-workspace";
export default async function SupplierRequestPage({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <ProductShell variant="supplier"><MobileBuyRequestWorkspace view="seller" initialId={Number(id)} /></ProductShell>; }
