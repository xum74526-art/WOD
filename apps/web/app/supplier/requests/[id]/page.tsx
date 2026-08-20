import { ProductShell } from "@/components/product-shell";
import { SupplierRequestDetail } from "@/components/supplier-request-detail";
export default async function SupplierRequestPage({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <ProductShell variant="supplier"><SupplierRequestDetail requestId={Number(id)} /></ProductShell>; }
