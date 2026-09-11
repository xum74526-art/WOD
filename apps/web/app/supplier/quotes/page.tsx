import { redirect } from "next/navigation";

export default function SupplierQuotesPage() {
  // Quote operations now live beside each request in the unified supplier workspace.
  redirect("/supplier/requests?scope=quoted");
}
