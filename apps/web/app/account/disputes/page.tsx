import type { Metadata } from "next";
import { DisputeWorkspace } from "@/components/dispute-workspace";

export const metadata: Metadata = { title: "争议工单" };
export default function DisputesPage() { return <DisputeWorkspace />; }
