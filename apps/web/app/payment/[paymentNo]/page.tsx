import { redirect } from "next/navigation";

export default function PaymentPage() {
  redirect("/account/wallet");
}
