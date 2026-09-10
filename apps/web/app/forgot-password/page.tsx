import { AuthShell } from "@/components/auth-shell";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "找回密碼", robots: { index: false, follow: false } };

export default function ForgotPasswordPage() {
  return <AuthShell mode="forgot" />;
}
