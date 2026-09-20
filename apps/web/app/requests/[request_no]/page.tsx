import { redirect } from "next/navigation";

export default function PublicRequestPage() {
  // Legacy request numbers cannot be mapped safely to the current numeric request IDs.
  redirect("/account/requests");
}
