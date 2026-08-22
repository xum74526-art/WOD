import { SiteHeader } from "@/components/site-header";
import { PublicRequestDetail } from "@/components/public-request-detail";

export default async function PublicRequestPage({ params }: { params: Promise<{ request_no: string }> }) {
  const { request_no } = await params;
  return <div className="site-page public-v2"><SiteHeader /><main className="public-data-page"><PublicRequestDetail requestNo={request_no} /></main></div>;
}
