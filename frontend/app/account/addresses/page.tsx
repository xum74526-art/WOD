import type { Metadata } from "next";
import { AddressWorkspace } from "@/components/address-workspace";

export const metadata: Metadata = { title: "地址管理" };
export default function AddressesPage() { return <AddressWorkspace />; }
