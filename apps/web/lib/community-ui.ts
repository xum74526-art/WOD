export const COMMUNITY_POST_MAX_LENGTH = 500;
export const COMMUNITY_MEDIA_MAX_FILES = 9;
export const COMMUNITY_IMAGE_MAX_BYTES = 5 * 1024 * 1024;
export const COMMUNITY_VIDEO_MAX_BYTES = 20 * 1024 * 1024;
export const COMMUNITY_VIDEO_MAX_DURATION_SECONDS = 5 * 60;
export const COMMUNITY_MEDIA_LIMIT_TEXT = "图片最多 9 张且单张最大 5MB；视频最长 5 分钟、最大 20MB，上传后统一转换为兼容 MP4";

type CommunityMediaFile = Pick<File, "name" | "size" | "type">;

export function isCommunityImageFile(file: CommunityMediaFile) {
  return file.type.toLowerCase().startsWith("image/") || /\.(jpe?g|png|webp)$/i.test(file.name);
}

export function isCommunityVideoFile(file: CommunityMediaFile) {
  return file.type.toLowerCase().startsWith("video/") || /\.(mp4|mov|webm)$/i.test(file.name);
}

export function communityMediaUploadError(files: readonly CommunityMediaFile[]) {
  if (files.length > COMMUNITY_MEDIA_MAX_FILES) {
    return `一次最多选择 ${COMMUNITY_MEDIA_MAX_FILES} 个文件，请重新选择`;
  }
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
  return source.replace(/(^|[^A-Z0-9_-])(?:WOD|ZTW)(?=$|[^A-Z0-9_-])/g, "$1算力星图");
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
