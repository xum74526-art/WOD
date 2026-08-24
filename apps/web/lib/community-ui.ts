export const COMMUNITY_POST_MAX_LENGTH = 500;

export function communityShareText(post: {
  content?: string | null;
  source_url?: string | null;
}) {
  const summary = String(post.content || "").trim().slice(0, 100);
  const source = String(post.source_url || "").trim();
  return [summary, source].filter(Boolean).join("\n");
}
