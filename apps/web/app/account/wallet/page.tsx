import type { Metadata } from "next";
import { PaymentWorkspace } from "@/components/payment-workspace";

export const metadata: Metadata = { title: "錢包與流水" };

export default function WalletPage() {
  return <PaymentWorkspace />;
}
