export const DEFAULT_PRODUCT_IMAGE = '/static/products/gpu.png'

/**
 * The first App Store build uses one project-owned neutral illustration for
 * every model.  Do not bundle or fetch vendor/product photography until its
 * redistribution rights and user-visible attribution have been recorded.
 */
export function fallbackProductImage(_gpuModel?: string | null): string {
  return DEFAULT_PRODUCT_IMAGE
}

/**
 * Server-supplied product imagery is intentionally ignored in this release so
 * an unreviewed URL or legacy bundled photo cannot enter the signed App package.
 */
export function resolveProductImage(_value?: string | null, gpuModel?: string | null): string {
  return fallbackProductImage(gpuModel)
}
