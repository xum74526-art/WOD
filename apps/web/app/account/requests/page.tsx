import type { Metadata } from "next";
import { MobileBuyRequestWorkspace } from "@/components/mobile-buy-request-workspace";
export const metadata: Metadata = { title: "我的需求" };

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function first(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function positiveNumber(value: string | string[] | undefined) {
  const parsed = Number(first(value));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

export default async function BuyerRequestsPage({ searchParams }: { searchParams: SearchParams }) {
  const query = await searchParams;
  const create = first(query.create) === "1";
  return <MobileBuyRequestWorkspace view="buyer" initialPrefill={create ? {
    create,
    product_id: positiveNumber(query.product_id),
    supplier_id: positiveNumber(query.supplier_id),
    source: first(query.source),
    product_name: first(query.product_name),
    seller_name: first(query.seller_name),
    gpu_model: first(query.gpu_model),
    gpu_variant: first(query.gpu_variant),
    quantity: positiveNumber(query.quantity),
    gpu_hours: positiveNumber(query.gpu_hours),
    region: first(query.region),
  } : undefined} />;
}
