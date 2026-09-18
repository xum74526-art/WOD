import { apiRequest, apiUploadRequest, retryIdempotentMutationOnce, type ApiUploadProgress } from "@/lib/api";
import { canonicalApiPath as path } from "@/lib/canonical-api";

export type CommunityPost = { id: number; user_id: number; content: string; images?: string[] | null; video?: string | null; video_duration?: number | null; topic?: string | null; origin?: string | null; content_type?: string | null; source_key?: string | null; source_name?: string | null; source_url?: string | null; source_author?: string | null; source_published_at?: string | null; summary?: string | null; video_url?: string | null; embed_url?: string | null; thumbnail_url?: string | null; canonical_url?: string | null; likes: number; comments: number; shares: number; created_at?: string; author_name?: string; author_avatar?: string; is_liked: boolean; is_following: boolean; is_own: boolean };
export type CommunityComment = { id: number; post_id: number; user_id: number; content: string; created_at?: string; author_name?: string; post_comments?: number; is_own: boolean };
export type CommunityReportTarget = "post" | "comment" | "user";
export type CommunityReportReason = "illegal" | "harassment" | "hate" | "sexual" | "violence" | "scam" | "privacy" | "copyright" | "spam" | "other";
export function communityMediaUrl(value?: string | null) { if (!value) return ""; return value.startsWith("/uploads/community/") ? path(value) : value; }
export function getCommunityPosts(tab = "recommend", page = 1, keyword = "") { const query = new URLSearchParams({ tab, page: String(page), page_size: "10", allow_aggregated: "false" }); if (keyword) query.set("keyword", keyword); return apiRequest<{ items: CommunityPost[]; total: number; page: number; page_size: number }>(path(`/community/posts?${query}`)); }
export function createCommunityPost(input: { content: string; topic?: string; images?: string[]; video?: string; video_duration?: number }) { return apiRequest<CommunityPost>(path("/community/posts"), { method: "POST", body: JSON.stringify(input) }); }
export function uploadCommunityMedia(file: File, onProgress?: (progress: ApiUploadProgress) => void) {
  const form = new FormData();
  form.set("media", file);
  return apiUploadRequest<{ url: string; kind: "image" | "video"; content_type: string; size: number; duration?: number | null; standardized?: boolean }>(
    path("/community/media/upload"),
    form,
    onProgress,
  );
}
export function setCommunityLike(id: number, liked: boolean) {
  const submit = () => apiRequest<{ liked: boolean; likes: number }>(path(`/community/posts/${id}/like`), {
    method: "POST",
    body: JSON.stringify({ liked }),
  });
  return retryIdempotentMutationOnce(submit);
}
export function setCommunityFollow(id: number, following: boolean) {
  const submit = () => apiRequest<{ following: boolean }>(path(`/community/users/${id}/follow`), {
    method: "POST",
    body: JSON.stringify({ following }),
  });
  return retryIdempotentMutationOnce(submit);
}
export function getCommunityComments(id: number) { return apiRequest<CommunityComment[]>(path(`/community/posts/${id}/comments`)); }
export function createCommunityComment(id: number, content: string, clientRequestId: string) {
  const submit = () => apiRequest<CommunityComment>(path(`/community/posts/${id}/comments`), {
    method: "POST",
    body: JSON.stringify({ content, client_request_id: clientRequestId }),
  });
  return retryIdempotentMutationOnce(submit);
}
export function reportCommunityContent(targetType: CommunityReportTarget, targetId: number, reason: CommunityReportReason = "other", details?: string) {
  const submit = () => apiRequest<{ report_id: number; status: string; hidden_for_reporter: boolean }>(path("/community/reports"), {
    method: "POST",
    body: JSON.stringify({ target_type: targetType, target_id: targetId, reason, details }),
  });
  return retryIdempotentMutationOnce(submit);
}
export function setCommunityBlock(id: number, blocked: boolean) {
  const submit = () => apiRequest<{ blocked: boolean }>(path(`/community/users/${id}/block`), {
    method: "POST",
    body: JSON.stringify({ blocked }),
  });
  return retryIdempotentMutationOnce(submit);
}
export function deleteCommunityPost(id: number) {
  const submit = () => apiRequest<{ deleted: boolean }>(path(`/community/posts/${id}`), { method: "DELETE" });
  return retryIdempotentMutationOnce(submit);
}
export function deleteCommunityComment(id: number) {
  const submit = () => apiRequest<{ deleted: boolean }>(path(`/community/comments/${id}`), { method: "DELETE" });
  return retryIdempotentMutationOnce(submit);
}
