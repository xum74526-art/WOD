export const DEFAULT_WEB_PRODUCT_IMAGE = "/images/gpu.png";

// Keep this allowlist in parity with the iOS and Android product-image maps.
// API image values are treated only as model identifiers; every accepted value
// resolves to a project-controlled, locally bundled path.
const VERIFIED_MODEL_IMAGES: Readonly<Record<string, string>> = {
  A10: "A100.jpg",
  A30: "A100.jpg",
  A40: "L40S.jpg",
  A100: "A100.jpg",
  A4000: "A6000.jpg",
  A5000: "A6000.jpg",
  A6000: "A6000.jpg",
  A800: "A800.jpg",
  B100: "H200.jpg",
  B200: "B200.jpg",
  B300: "B300.jpg",
  GRIDK1: "GRIDK1.jpg",
  GRIDK2: "GRIDK2.jpg",
  GTX1080: "GTX1080.jpg",
  GTX1080TI: "GTX1080Ti.jpg",
  H100: "H100.jpg",
  H20: "H20.jpg",
  H200: "H200.jpg",
  H800: "H800.jpg",
  K40: "K40.jpg",
  K80: "K80.jpg",
  L4: "L4.jpg",
  L40: "L40S.jpg",
  L40S: "L40S.jpg",
  M40: "M40.jpg",
  MI300X: "MI300X.jpg",
  MTTS4000: "MTTS4000.jpg",
  P4: "P4.jpg",
  P40: "P40.jpg",
  P100: "P100.jpg",
  RTX2000: "RTX2080Ti.jpg",
  RTX2060: "RTX2060.jpg",
  RTX2070: "RTX2060.jpg",
  RTX2070SUPER: "RTX2060.jpg",
  RTX2080: "RTX2080Ti.jpg",
  RTX2080TI: "RTX2080Ti.jpg",
  RTX3050: "RTX3070.jpg",
  RTX3060: "RTX3070.jpg",
  RTX3060TI: "RTX3070.jpg",
  RTX3070: "RTX3070.jpg",
  RTX3070TI: "RTX3070.jpg",
  RTX3080: "RTX3080.jpg",
  RTX3080TI: "RTX3080Ti.jpg",
  RTX3090: "RTX3090.jpg",
  RTX3090TI: "RTX3090.jpg",
  RTX4000: "RTXPRO6000.jpg",
  RTX4000ADA: "RTX4000Ada.jpg",
  RTX4060: "RTX4070.jpg",
  RTX4060TI: "RTX4070.jpg",
  RTX4070: "RTX4070.jpg",
  RTX4070SUPER: "RTX4070.jpg",
  RTX4070TI: "RTX4070.jpg",
  RTX4080: "RTX4080.jpg",
  RTX4080SUPER: "RTX4080.jpg",
  RTX4090: "RTX4090.jpg",
  RTX4090D: "RTX4090D.jpg",
  RTX4500: "RTXPRO6000.jpg",
  RTX5000: "RTXPRO6000.jpg",
  RTX5000ADA: "RTX5000Ada.jpg",
  RTX5060: "RTX5060Ti.jpg",
  RTX5060TI: "RTX5060Ti.jpg",
  RTX5070: "RTX5070.jpg",
  RTX5070TI: "RTX5070.jpg",
  RTX5080: "RTX5080.jpg",
  RTX5090: "RTX5090.jpg",
  RTX5880: "RTXPRO6000.jpg",
  RTX6000: "RTXPRO6000.jpg",
  RTX6000ADA: "RTX6000Ada.jpg",
  RTXPRO6000: "RTXPRO6000.jpg",
  T4: "T4.jpg",
  V100: "V100.jpg",
  VGPU32: "vGPU32.jpg",
  VGPU48: "vGPU48.jpg",
};

function modelKey(value?: string | null): string {
  return String(value ?? "").replace(/[^A-Za-z0-9]/g, "").toUpperCase();
}

function bundledImageForModel(value?: string | null): string | null {
  const bundled = VERIFIED_MODEL_IMAGES[modelKey(value)];
  return bundled ? `/images/gpu/${bundled}` : null;
}

/** Return the exact approved local image for a known model. */
export function fallbackWebProductImage(gpuModel?: string | null): string {
  return bundledImageForModel(gpuModel) ?? DEFAULT_WEB_PRODUCT_IMAGE;
}

/**
 * Resolve only allowlisted API GPU paths or their approved Web-local form.
 * Remote schemes, traversal, query strings, and unknown filenames use the
 * exact model mapping when possible and the neutral image otherwise.
 */
export function resolveWebProductImage(value?: string | null, gpuModel?: string | null): string {
  const source = String(value ?? "").trim();
  if (source === DEFAULT_WEB_PRODUCT_IMAGE) return DEFAULT_WEB_PRODUCT_IMAGE;

  const gpuPath = source.match(/^\/(?:static\/gpu|images\/gpu)\/([^/?#]+)\.(?:jpe?g|png|webp)$/i);
  if (gpuPath) return bundledImageForModel(gpuPath[1]) ?? fallbackWebProductImage(gpuModel);

  return fallbackWebProductImage(gpuModel);
}
