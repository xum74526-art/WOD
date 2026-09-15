import { redirect } from "next/navigation";
import { legacyRequestCreateHref, type RequestSearchParams } from "@/lib/request-navigation";

export default async function NewRequestPage({ searchParams }: { searchParams: Promise<RequestSearchParams> }) {
  redirect(legacyRequestCreateHref(await searchParams));
}
