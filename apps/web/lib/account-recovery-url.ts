export type RecoveryTokenSource = "fragment" | null;

export type RecoveryTokenFromUrl = {
  token: string;
  source: RecoveryTokenSource;
  cleanPath: string;
};

/**
 * Read a short-lived recovery proof without ever persisting it. Only fragment
 * values are accepted because browsers do not send them to the Web server.
 */
export function recoveryTokenFromUrl(
  href: string,
  fragmentKeys: readonly string[] = ["token", "kai_recovery_token"],
): RecoveryTokenFromUrl {
  const url = new URL(href);
  const fragment = new URLSearchParams(url.hash.startsWith("#") ? url.hash.slice(1) : url.hash);
  let token = "";
  for (const key of fragmentKeys) {
    const value = fragment.get(key);
    if (value) {
      token = value;
      break;
    }
  }
  const source: RecoveryTokenSource = token ? "fragment" : null;

  for (const key of fragmentKeys) {
    fragment.delete(key);
    // Never accept query-delivered proofs, but remove them from the visible
    // URL in case a malformed or manually copied link included one.
    url.searchParams.delete(key);
  }
  const cleanFragment = fragment.toString();
  const cleanPath = `${url.pathname}${url.search}${cleanFragment ? `#${cleanFragment}` : ""}`;
  return {
    token: token.length >= 32 && token.length <= 256 ? token : "",
    source,
    cleanPath,
  };
}
