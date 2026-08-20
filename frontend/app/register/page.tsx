import type { Metadata } from "next";
import { AuthShell } from "@/components/auth-shell";

export const metadata: Metadata = { title: "注册" };

export default function RegisterPage() {
  return <AuthShell mode="register" />;
}
