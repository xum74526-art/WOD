import type { KaiLocale } from "./language.ts";
import { toTraditionalChinese } from "./traditional-chinese.ts";

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

const INTERNAL_REGION_EN: Array<[string, string]> = [
  ["全球 / 未披露", "Global / Undisclosed"],
  ["全球／未披露", "Global / Undisclosed"],
  ["全球/未披露", "Global / Undisclosed"],
  ["中国大陆", "Mainland China"],
  ["华北", "North China"],
  ["华东", "East China"],
  ["华中", "Central China"],
  ["华南", "South China"],
  ["东北", "Northeast China"],
  ["西北", "Northwest China"],
  ["西南", "Southwest China"],
  ["亚太", "Asia Pacific"],
  ["北美", "North America"],
  ["欧洲", "Europe"],
  ["中东", "Middle East"],
  ["南美", "South America"],
  ["非洲", "Africa"],
  ["海外", "Overseas"],
  ["未披露", "Undisclosed"],
];

export function communityDisplayText(
  value?: string | null,
  sourceKey?: string | null,
  locale: KaiLocale = "zh-Hans",
) {
  const source = String(value || "");
  if (sourceKey !== "wod-market") return source;
  const branded = source
    .replace(/(?:WOD|ZTW)(?:资讯|資訊)/g, "KAI星算平台行情")
    .replace(/(^|[^A-Z0-9_-])(?:WOD|ZTW)(?=$|[^A-Z0-9_-])/g, "$1KAI星算");
  if (locale === "zh-Hant") return toTraditionalChinese(branded);
  if (locale !== "en") return branded;

  let localized = branded
    .replace(/KAI星算平台行情|算力星圖平台行情/g, "KAI Platform Market")
    .replace(/KAI星算算力行情/g, "KAI Compute Market")
    .replace(/(?:KAI星算|算力星圖)(?:平台)?(?:算力)?(?:行情|资讯|資訊)/g, "KAI Compute Market")
    .replace(/Compute Star Map(?:\s+market)?/gi, "KAI Compute Market")
    .replace(/KAI星算\s+market/gi, "KAI Compute Market")
    .replace(/KAI星算/g, "KAI");
  for (const [from, to] of INTERNAL_REGION_EN) localized = localized.replaceAll(from, to);
  return localized;
}

type CommunityLocalizedPost = {
  content?: string | null;
  content_en?: string | null;
  topic?: string | null;
  topic_en?: string | null;
  origin?: string | null;
  source_key?: string | null;
};

function communityPlatformText(
  value: string,
  sourceKey: string | null | undefined,
  origin: string | null | undefined,
  locale: KaiLocale,
) {
  const platformOwned = origin === "internal" || origin === "aggregated" || Boolean(sourceKey);
  if (!platformOwned) return value;
  const localized = communityDisplayText(value, sourceKey, locale);
  return locale === "zh-Hant" ? toTraditionalChinese(localized) : localized;
}

export function communityPostContent(post: CommunityLocalizedPost, locale: KaiLocale) {
  const source = locale === "en" && post.origin !== "user" && post.content_en
    ? post.content_en
    : String(post.content || "");
  return communityPlatformText(source, post.source_key, post.origin, locale);
}

export function communityPostTopic(post: CommunityLocalizedPost, locale: KaiLocale) {
  const source = locale === "en" && post.origin !== "user" && post.topic_en
    ? post.topic_en
    : String(post.topic || "");
  return communityPlatformText(source, post.source_key, post.origin, locale);
}

export function communityShareText(post: {
  content?: string | null;
  content_en?: string | null;
  origin?: string | null;
  source_url?: string | null;
  source_key?: string | null;
}, locale: KaiLocale = "zh-Hans") {
  const summary = communityPostContent(post, locale).trim().slice(0, 100);
  const source = String(post.source_url || "").trim();
  return [summary, source].filter(Boolean).join("\n");
}
