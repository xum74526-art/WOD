const WEB_GPU_IMAGES = {
  accelerator: "/images/a800.jpg",
  datacenter: "/images/h100.jpg",
  geforce: "/images/rtx4090.jpg",
  nextGeneration: "/images/rtx5090.jpg",
} as const;

function modelKey(value?: string | null) {
  return String(value ?? "").replace(/[^A-Za-z0-9]/g, "").toUpperCase();
}

/**
 * Web keeps a compact, verified fallback set instead of assuming that every
 * App-bundled, case-sensitive filename also exists below Next.js `public`.
 * B300 belongs to the current data-centre accelerator family and must never
 * fall through to the old generic green-board placeholder.
 */
export function fallbackWebProductImage(gpuModel?: string | null) {
  const key = modelKey(gpuModel);
  if (/^(B100|B200|B300|H20|H100|H200|H800|L4|L40|L40S)/.test(key)) return WEB_GPU_IMAGES.datacenter;
  if (/^(RTX50|GB)/.test(key)) return WEB_GPU_IMAGES.nextGeneration;
  if (/^(RTX|GTX|VGPU)/.test(key)) return WEB_GPU_IMAGES.geforce;
  return WEB_GPU_IMAGES.accelerator;
}

/** Only render API-controlled image URLs that are safe in an image context. */
export function resolveWebProductImage(value?: string | null, gpuModel?: string | null) {
  const fallback = fallbackWebProductImage(gpuModel);
  const source = String(value ?? "").trim();
  if (!source) return fallback;

  // App asset paths are not Web public paths. Resolve them by GPU identity so
  // a valid native filename cannot become a broken browser image.
  if (/^\/static\/gpu\//i.test(source) || /^\/static\/products\/gpu\.png$/i.test(source)) return fallback;
  if (/^\/images\/[A-Za-z0-9._/-]+\.(?:png|jpe?g|webp)$/i.test(source)) return source;
  // Backend-relative static paths are not exposed by the Next/nginx Web
  // origin. Let those paths fall back locally instead of rendering a 404.

  try {
    const url = new URL(source);
    if (url.protocol === "https:") return url.toString();
  } catch {
    // Invalid and non-URL values use the bundled fallback.
  }
  return fallback;
}
