import type { Metadata } from "next";
import { ApiKeyWorkspace } from "@/components/api-key-workspace";

export const metadata: Metadata = { title: "API Key" };
export default function ApiKeysPage() { return <ApiKeyWorkspace />; }
