export const DEFAULT_PRODUCT_IMAGE = '/static/products/gpu.png'

const VERIFIED_MODEL_IMAGES: Record<string, string> = {
  A10: 'A10.jpg',
  A30: 'A30.jpg',
  A40: 'A40.jpg',
  A100: 'A100.jpg',
  A4000: 'A4000.jpg',
  A5000: 'A5000.jpg',
  A6000: 'A6000.jpg',
  RTXA6000: 'A6000.jpg',
  A800: 'A800.jpg',
  B200: 'B200.jpg',
  B300: 'B300.jpg',
  GRIDK1: 'GRIDK1.jpg',
  GRIDK2: 'GRIDK2.jpg',
  GTX1080: 'GTX1080.jpg',
  GTX1080TI: 'GTX1080Ti.jpg',
  H100: 'H100.jpg',
  H20: 'H20.jpg',
  H200: 'H200.jpg',
  H800: 'H800.jpg',
  K40: 'K40.jpg',
  K80: 'K80.jpg',
  L4: 'L4.jpg',
  L40: 'L40.jpg',
  L40S: 'L40S.jpg',
  M40: 'M40.jpg',
  MI300X: 'MI300X.jpg',
  MTTS4000: 'MTTS4000.jpg',
  P4: 'P4.jpg',
  P40: 'P40.jpg',
  P100: 'P100.jpg',
  RTX2060: 'RTX2060.jpg',
  RTX2070: 'RTX2070.jpg',
  RTX2080TI: 'RTX2080Ti.jpg',
  RTX3060: 'RTX3060.jpg',
  RTX3070: 'RTX3070.jpg',
  RTX3070TI: 'RTX3070Ti.jpg',
  RTX3080: 'RTX3080.jpg',
  RTX3080TI: 'RTX3080Ti.jpg',
  RTX3090: 'RTX3090.jpg',
  RTX4000ADA: 'RTX4000Ada.jpg',
  RTX4070: 'RTX4070.jpg',
  RTX4070TI: 'RTX4070Ti.jpg',
  RTX4080: 'RTX4080.jpg',
  RTX4090: 'RTX4090.jpg',
  RTX4090D: 'RTX4090D.jpg',
  RTX5000ADA: 'RTX5000Ada.jpg',
  RTX5090: 'RTX5090.jpg',
  RTX6000ADA: 'RTX6000Ada.jpg',
  RTXPRO6000: 'RTXPRO6000.jpg',
  T4: 'T4.jpg',
  V100: 'V100.jpg',
  VGPU32: 'vGPU32.jpg',
  VGPU48: 'vGPU48.jpg',
}

function modelKey(value?: string | null): string {
  let key = String(value || '').replace(/[^A-Za-z0-9]/g, '').toUpperCase()
  let previous = ''
  while (key !== previous) {
    previous = key
    key = key.replace(/^(NVIDIA|AMD|GEFORCE|TESLA|QUADRO)/, '')
  }
  return key
}

/**
 * Return an App-bundled image for the exact model when one has been visually
 * verified, otherwise use a real photo from the closest GPU family.  This is
 * preferable to requesting a case-sensitive/non-existent Android asset such
 * as RTX5070TI.jpg and preferable to showing the same circuit-board placeholder
 * for every new SKU.
 */
export function fallbackProductImage(gpuModel?: string | null): string {
  const key = modelKey(gpuModel)
  const exact = VERIFIED_MODEL_IMAGES[key]
  if (exact) return `/static/gpu/${exact}`

  if (/^RTX50(60|60TI|70|70TI|80)$/.test(key)) return '/static/gpu/RTX5090.jpg'
  if (/^RTX40(60|60TI|70|70TI|80TI)$/.test(key)) return '/static/gpu/RTX4080.jpg'
  if (/^RTX30/.test(key)) return '/static/gpu/RTX3090.jpg'
  if (/^RTX20/.test(key)) return '/static/gpu/RTX2080Ti.jpg'
  if (/^RTX(4000|4500|5000|5880|6000)/.test(key)) return '/static/gpu/RTXPRO6000.jpg'
  if (/^A(10|30|40|4000|5000)$/.test(key)) return '/static/gpu/A6000.jpg'
  if (/^L(4|40)$/.test(key)) return '/static/gpu/L40S.jpg'
  return DEFAULT_PRODUCT_IMAGE
}

/**
 * Product images are persisted by the API as deployment-independent paths.
 * The legacy generic path (`/static/gpu/gpu.png`) never existed in the App
 * bundle, so Android rendered a large empty image block while H5 could appear
 * to work through its dev server fallback.
 */
export function resolveProductImage(value?: string | null, gpuModel?: string | null): string {
  const source = String(value || '').trim()
  const fallback = fallbackProductImage(gpuModel)
  if (!source) return fallback
  if (/^\/static\/gpu\/gpu\.png$/i.test(source)) return fallback
  const gpuPath = source.match(/^\/static\/gpu\/([^/?#]+)\.(?:jpe?g|png|webp)$/i)
  if (gpuPath) {
    const bundled = VERIFIED_MODEL_IMAGES[modelKey(gpuPath[1])]
    return bundled ? `/static/gpu/${bundled}` : fallback
  }
  if (/^\/static\/products\/[A-Za-z0-9._-]+\.(?:png|jpe?g|webp)$/i.test(source)) return source
  if (/^https:\/\//i.test(source)) return source
  if (/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//i.test(source)) return source
  return fallback
}
