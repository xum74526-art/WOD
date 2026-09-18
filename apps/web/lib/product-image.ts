export const DEFAULT_WEB_PRODUCT_IMAGE = "/images/gpu.png";

/**
 * The first public release uses one project-owned neutral illustration until
 * redistribution rights for product photography are fully documented.
 */
export function fallbackWebProductImage(_gpuModel?: string | null) {
  return DEFAULT_WEB_PRODUCT_IMAGE;
}

/** Ignore unreviewed server image paths for the first public release. */
export function resolveWebProductImage(_value?: string | null, gpuModel?: string | null) {
  return fallbackWebProductImage(gpuModel);
}
