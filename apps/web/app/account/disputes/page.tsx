import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = { title: "爭議工單" };
export default function DisputesPage() { redirect("/account/orders"); }
