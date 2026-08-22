const DEVELOPMENT_API_ORIGIN = "https://wod.kai.com";

function isLocalHostname(hostname: string) {
  if (["127.0.0.1", "localhost", "::1"].includes(hostname)) return true;
  const parts = hostname.split(".").map(Number);
  return parts.length === 4
    && parts.every((part) => Number.isInteger(part) && part >= 0 && part <= 255)
    && (parts[0] === 10
      || (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31)
      || (parts[0] === 192 && parts[1] === 168));
}

export function resolveApiOrigin(environment: NodeJS.ProcessEnv = process.env) {
  const configured = environment.API_ORIGIN?.trim();
  if (environment.NODE_ENV === "production" && !configured) {
    throw new Error("API_ORIGIN is required in production");
  }

  const url = new URL(configured || DEVELOPMENT_API_ORIGIN);
  if (url.username || url.password || url.search || url.hash || !["", "/"].includes(url.pathname)) {
    throw new Error("API_ORIGIN must contain only the backend origin without credentials, path, query, or fragment");
  }

  const local = isLocalHostname(url.hostname);
  const allowInsecureLoopback = environment.API_ALLOW_INSECURE_HTTP === "true" && local;
  if (url.protocol !== "https:" && !(url.protocol === "http:" && allowInsecureLoopback)) {
    throw new Error("API_ORIGIN must use HTTPS; local/private HTTP must be enabled explicitly");
  }
  return url.origin;
}
