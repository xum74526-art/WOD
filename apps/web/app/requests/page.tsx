import { redirect } from "next/navigation";

export default function RequestsPage() {
  // The retired public board has no canonical API; keep old bookmarks on a working flow.
  redirect("/account/requests");
}
