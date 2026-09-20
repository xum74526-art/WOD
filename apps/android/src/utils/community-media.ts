export const COMMUNITY_IMAGE_MAX_BYTES = 5 * 1024 * 1024
export const COMMUNITY_VIDEO_MAX_BYTES = 20 * 1024 * 1024

type FileWithOptionalSize = { size?: unknown }

function isSizeOverLimit(size: unknown, maxBytes: number): boolean {
  const bytes = Number(size)
  return Number.isFinite(bytes) && bytes > maxBytes
}

export function hasOversizedCommunityImage(
  tempFiles: FileWithOptionalSize | FileWithOptionalSize[] | null | undefined,
): boolean {
  const files = Array.isArray(tempFiles) ? tempFiles : tempFiles ? [tempFiles] : []
  return files.some(file => isSizeOverLimit(file.size, COMMUNITY_IMAGE_MAX_BYTES))
}

export function isCommunityVideoTooLarge(size: unknown): boolean {
  return isSizeOverLimit(size, COMMUNITY_VIDEO_MAX_BYTES)
}
