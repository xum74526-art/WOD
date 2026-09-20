import { ProductShell } from "@/components/product-shell";

export default function AccountLayout({ children }: { children: React.ReactNode }) {
  return <ProductShell>{children}</ProductShell>;
}
