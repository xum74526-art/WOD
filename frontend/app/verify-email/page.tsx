import type { Metadata } from "next";
import { EmailVerificationResult } from "@/components/email-verification-result";

export const metadata: Metadata = { title: "验证邮箱" };
export default async function VerifyEmailPage({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const { token = "" } = await searchParams;
  return <EmailVerificationResult token={token}/>;
}
