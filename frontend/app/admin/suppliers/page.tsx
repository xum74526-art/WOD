import type { Metadata } from "next";
import { SupplierReview } from "@/components/supplier-review";

export const metadata: Metadata = { title: "商家准入审核" };
export default function AdminSuppliersPage() { return <SupplierReview />; }
