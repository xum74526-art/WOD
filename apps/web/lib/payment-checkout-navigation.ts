const QIXIANG_CHECKOUT_PATH = /^\/api\/payments\/qixiang\/checkout\/([A-Za-z0-9_-]{32,128})$/;
const CANONICAL_QIXIANG_CHECKOUT_PATH = /^\/api\/v1\/canonical\/payments\/qixiang\/checkout\/([A-Za-z0-9_-]{32,128})$/;

export function qixiangCheckoutHref(checkoutUrl: string, webOrigin: string): string | null {
  let parsed: URL;
  let origin: URL;
  try {
    parsed = new URL(checkoutUrl, webOrigin);
    origin = new URL(webOrigin);
  } catch {
    return null;
  }
  if (
    parsed.origin !== origin.origin
    || parsed.username
    || parsed.password
    || parsed.search
    || parsed.hash
  ) {
    return null;
  }
  const match = parsed.pathname.match(QIXIANG_CHECKOUT_PATH)
    || parsed.pathname.match(CANONICAL_QIXIANG_CHECKOUT_PATH);
  return match
    ? `/api/v1/canonical/payments/qixiang/checkout/${match[1]}`
    : null;
}
