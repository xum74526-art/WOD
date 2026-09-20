import { ProductShell } from "@/components/product-shell";
import { MobileBuyRequestWorkspace } from "@/components/mobile-buy-request-workspace";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function SupplierRequestsPage({ searchParams }: { searchParams: SearchParams }) {
  const query = await searchParams;
  const scope = Array.isArray(query.scope) ? query.scope[0] : query.scope;
  return <ProductShell variant="supplier"><MobileBuyRequestWorkspace view="seller" initialSellerScope={scope === "quoted" ? "quoted" : "all"} /></ProductShell>;
}
