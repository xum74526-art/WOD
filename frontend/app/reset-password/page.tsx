import { AuthShell } from "@/components/auth-shell";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "重置密码", robots: { index: false, follow: false } };

export default function ResetPasswordPage() {
  return <AuthShell mode="reset" />;
}
