import type { Metadata } from "next";
import { CommentModeration } from "@/components/comment-moderation";

export const metadata: Metadata = { title: "內容治理" };
export default function AdminModerationPage() { return <CommentModeration />; }
