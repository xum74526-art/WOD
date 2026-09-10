/**
 * Present legacy WOD-prefixed business references under the current ZTW brand.
 * The original value must still be used for API requests, copying, and storage.
 */
export function displayBusinessReference(value?: string | null) {
  return String(value || "").replace(/^WOD(?=[A-Z0-9-])/i, "ZTW");
}
