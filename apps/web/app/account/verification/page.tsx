import type { Metadata } from "next";
import { MobileVerificationWorkspace } from "@/components/mobile-verification-workspace";

export const metadata: Metadata = { title: "实名认证" };

export default function VerificationPage() {
  return <MobileVerificationWorkspace />;
}
