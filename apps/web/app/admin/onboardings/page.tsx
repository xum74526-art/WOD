import type { Metadata } from "next";
import { AdminOnboardingWorkspace } from "@/components/admin-onboarding-workspace";

export const metadata: Metadata = { title: "设备托管审核" };

export default function AdminOnboardingsPage() {
  return <AdminOnboardingWorkspace/>;
}
