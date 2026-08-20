import type { Metadata } from "next";
import { PaymentWorkspace } from "@/components/payment-workspace";

export const metadata: Metadata = { title: "钱包与流水" };

export default function WalletPage() {
  return <PaymentWorkspace />;
}
