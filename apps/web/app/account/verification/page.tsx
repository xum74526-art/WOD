import type { Metadata } from "next";
import { MobileVerificationWorkspace } from "@/components/mobile-verification-workspace";

export const metadata: Metadata = { title: "實名認證" };

export default function VerificationPage() {
  return <MobileVerificationWorkspace />;
}
