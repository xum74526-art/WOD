/**
 * Present legacy WOD/ZTW-prefixed business references under the current 算力星图 brand.
 * The original value must still be used for API requests, copying, and storage.
 */
export function displayBusinessReference(value?: string | null) {
  return String(value || "").replace(/^(?:WOD|ZTW)(?=[A-Z0-9-])/i, "算力星图");
}
