import type { Metadata } from "next";
import { AdminKycWorkspace } from "@/components/admin-kyc-workspace";

export const metadata: Metadata = { title: "實名認證稽覈" };
export default function AdminKycPage() { return <AdminKycWorkspace />; }
