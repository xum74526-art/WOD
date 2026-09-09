export const COMMUNITY_POST_MAX_LENGTH = 500;

export function communityDisplayText(value?: string | null, sourceKey?: string | null) {
  const source = String(value || "");
  if (sourceKey !== "wod-market") return source;
  return source.replace(/(^|[^A-Z0-9_-])WOD(?=$|[^A-Z0-9_-])/g, "$1ZTW");
}

export function communityShareText(post: {
  content?: string | null;
  source_url?: string | null;
  source_key?: string | null;
}) {
  const summary = communityDisplayText(post.content, post.source_key).trim().slice(0, 100);
  const source = String(post.source_url || "").trim();
  return [summary, source].filter(Boolean).join("\n");
}
