import type { Metadata } from "next";
import { MobileAssetsWorkspace } from "@/components/mobile-assets-workspace";

export const metadata: Metadata = { title: "個人資產" };

export default function AccountAssetsPage() { return <MobileAssetsWorkspace />; }
