import { MobileBuyRequestWorkspace } from "@/components/mobile-buy-request-workspace";
export default async function BuyerRequestPage({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <MobileBuyRequestWorkspace view="buyer" initialId={Number(id)} />; }
