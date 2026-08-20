import type { Metadata } from "next";
import { PrivateFilesWorkspace } from "@/components/private-files-workspace";

export const metadata: Metadata = { title: "私有文件" };

export default function PrivateFilesPage() {
  return <PrivateFilesWorkspace />;
}
