export function loginHref(returnTo: string) {
  const safePath = returnTo.startsWith("/") && !returnTo.startsWith("//") ? returnTo : "/";
  return `/login?return_to=${encodeURIComponent(safePath)}`;
}
