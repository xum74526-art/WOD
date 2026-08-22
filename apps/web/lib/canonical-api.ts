/**
 * Same-origin Web BFF route for the canonical FastAPI `/api` contract.
 * The browser never receives the backend bearer token; the BFF reads it from
 * an HttpOnly cookie and forwards the request to API_ORIGIN.
 */
export function canonicalApiPath(path: string) {
  const pathname = path.split(/[?#]/, 1)[0];
  let decodedPathname = "";
  try {
    decodedPathname = decodeURIComponent(pathname);
  } catch {
    throw new Error("Canonical API paths must be valid URI paths");
  }
  if (!path.startsWith("/") || path.startsWith("//") || decodedPathname.split("/").includes("..")) {
    throw new Error("Canonical API paths must be safe absolute paths");
  }
  return `/api/v1/canonical${path}`;
}
