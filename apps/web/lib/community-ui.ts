export const COMMUNITY_POST_MAX_LENGTH = 500;
export const COMMUNITY_IMAGE_MAX_BYTES = 5 * 1024 * 1024;
export const COMMUNITY_VIDEO_MAX_BYTES = 20 * 1024 * 1024;
export const COMMUNITY_MEDIA_LIMIT_TEXT = "图片最大 5MB，视频最大 20MB";

type CommunityMediaFile = Pick<File, "name" | "size" | "type">;

export function isCommunityImageFile(file: CommunityMediaFile) {
  return file.type.toLowerCase().startsWith("image/") || /\.(jpe?g|png|webp)$/i.test(file.name);
}

export function isCommunityVideoFile(file: CommunityMediaFile) {
  return file.type.toLowerCase().startsWith("video/") || /\.(mp4|webm)$/i.test(file.name);
}

export function communityMediaUploadError(files: readonly CommunityMediaFile[]) {
  for (const file of files) {
    if (isCommunityImageFile(file) && file.size > COMMUNITY_IMAGE_MAX_BYTES) {
      return "社区图片不能超过 5MB，请重新选择";
    }
    if (isCommunityVideoFile(file) && file.size > COMMUNITY_VIDEO_MAX_BYTES) {
      return "社区视频不能超过 20MB，请重新选择";
    }
  }
  return "";
}

export async function uploadCommunityMediaBatch<T>(
  files: readonly File[],
  upload: (file: File) => Promise<T>,
) {
  const validationError = communityMediaUploadError(files);
  if (validationError) throw new Error(validationError);

  const uploaded: T[] = [];
  for (const file of files) uploaded.push(await upload(file));
  return uploaded;
}

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
