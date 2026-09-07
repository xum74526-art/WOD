import type { Metadata } from "next";
import { EmailVerificationResult } from "@/components/email-verification-result";

export const metadata: Metadata = { title: "验证绑定邮箱", robots: { index: false, follow: false } };
export default function VerifyEmailPage() {
  return <EmailVerificationResult/>;
}
