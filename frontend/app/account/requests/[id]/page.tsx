import { BuyerRequestDetail } from "@/components/buyer-request-detail";
export default async function BuyerRequestPage({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <BuyerRequestDetail requestId={Number(id)} />; }
