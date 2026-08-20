import type { Metadata } from "next";
import { ResourceReview } from "@/components/resource-review";

export const metadata: Metadata = { title: "算力资源审核" };
export default function AdminResourcesPage() { return <ResourceReview />; }
