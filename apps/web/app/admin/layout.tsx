import { ProductShell } from "@/components/product-shell";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <ProductShell variant="admin">{children}</ProductShell>;
}
