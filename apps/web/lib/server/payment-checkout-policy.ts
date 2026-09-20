const DEFAULT_QIXIANG_CHECKOUT_HOSTS = ["api.payqixiang.cn"] as const;
const HOSTNAME = /^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;

export function paymentCheckoutAllowedHosts(
  environment: { PAYMENT_CHECKOUT_ALLOWED_HOSTS?: string } = process.env as { PAYMENT_CHECKOUT_ALLOWED_HOSTS?: string },
) {
  const configured = String(environment.PAYMENT_CHECKOUT_ALLOWED_HOSTS || "")
    .split(",")
    .map((value) => value.trim().toLowerCase())
    .filter((value) => HOSTNAME.test(value));
  return new Set([...DEFAULT_QIXIANG_CHECKOUT_HOSTS, ...configured]);
}

export function allowedPaymentCheckoutRedirect(
  location: string,
  allowedHosts: ReadonlySet<string>,
): URL | null {
  let destination: URL;
  try {
    destination = new URL(location);
  } catch {
    return null;
  }
  if (
    destination.protocol !== "https:"
    || destination.username
    || destination.password
    || (destination.port && destination.port !== "443")
    || !allowedHosts.has(destination.hostname.toLowerCase())
  ) {
    return null;
  }
  return destination;
}

export function paymentCheckoutClientIp(headers: { get(name: string): string | null }) {
  // Production Next listens on 127.0.0.1 and Nginx overwrites X-Real-IP with
  // $remote_addr. Never forward a chain or an unvalidated client string.
  const candidate = String(headers.get("x-real-ip") || "").trim();
  return candidate && !candidate.includes(",") && isIP(candidate) ? candidate : null;
}
import { isIP } from "node:net";
