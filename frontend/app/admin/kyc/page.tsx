import type { Metadata } from "next";
import { AdminKycWorkspace } from "@/components/admin-kyc-workspace";

export const metadata: Metadata = { title: "实名认证审核" };
export default function AdminKycPage() { return <AdminKycWorkspace />; }
