import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = { title: "争议工单" };
export default function DisputesPage() { redirect("/account/orders"); }
