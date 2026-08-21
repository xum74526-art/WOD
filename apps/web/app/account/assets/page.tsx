import type { Metadata } from "next";
import { MobileAssetsWorkspace } from "@/components/mobile-assets-workspace";

export const metadata: Metadata = { title: "个人资产" };

export default function AccountAssetsPage() { return <MobileAssetsWorkspace />; }
