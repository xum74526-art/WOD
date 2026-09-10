import type { Metadata } from "next";
import { TeamWorkspace } from "@/components/team-workspace";

export const metadata: Metadata = { title: "團隊管理" };
export default function TeamsPage() { return <TeamWorkspace />; }
