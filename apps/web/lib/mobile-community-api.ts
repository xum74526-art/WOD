import { apiRequest } from "@/lib/api";

const path = (value: string) => `/api/v1/mobile${value}`;
export type CommunityPost = { id: number; user_id: number; content: string; images?: string[] | null; video?: string | null; video_duration?: number | null; topic?: string | null; origin?: string | null; content_type?: string | null; source_name?: string | null; source_url?: string | null; source_author?: string | null; source_published_at?: string | null; summary?: string | null; video_url?: string | null; embed_url?: string | null; thumbnail_url?: string | null; canonical_url?: string | null; likes: number; comments: number; shares: number; created_at?: string; author_name?: string; author_avatar?: string; is_liked: boolean; is_following: boolean; is_own: boolean };
export type CommunityComment = { id: number; post_id: number; user_id: number; content: string; created_at?: string; author_name?: string };
export function communityMediaUrl(value?: string | null) { if (!value) return ""; return value.startsWith("/uploads/community/") ? path(value) : value; }
export function getCommunityPosts(tab = "recommend", page = 1, keyword = "") { const query = new URLSearchParams({ tab, page: String(page), page_size: "10" }); if (keyword) query.set("keyword", keyword); return apiRequest<{ items: CommunityPost[]; total: number; page: number; page_size: number }>(path(`/community/posts?${query}`)); }
export function createCommunityPost(input: { content: string; topic?: string; images?: string[]; video?: string; video_duration?: number }) { return apiRequest<CommunityPost>(path("/community/posts"), { method: "POST", body: JSON.stringify(input) }); }
export function uploadCommunityMedia(file: File) { const form = new FormData(); form.set("media", file); return apiRequest<{ url: string; kind: "image" | "video"; content_type: string; size: number }>(path("/community/media/upload"), { method: "POST", body: form }); }
export function toggleCommunityLike(id: number) { return apiRequest<{ liked: boolean; likes: number }>(path(`/community/posts/${id}/like`), { method: "POST" }); }
export function toggleCommunityFollow(id: number) { return apiRequest<{ following: boolean }>(path(`/community/users/${id}/follow`), { method: "POST" }); }
export function getCommunityComments(id: number) { return apiRequest<CommunityComment[]>(path(`/community/posts/${id}/comments`)); }
export function createCommunityComment(id: number, content: string) { return apiRequest<CommunityComment>(path(`/community/posts/${id}/comments`), { method: "POST", body: JSON.stringify({ content }) }); }
