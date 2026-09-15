const RETURN_PATH_ORIGIN = "https://return-path.invalid";
const UNSAFE_RETURN_PATH_CHARACTERS = /[\u0000-\u001f\u007f\\]/;

export function safeReturnPath(value: unknown): string {
  if (
    typeof value !== "string"
    || !value.startsWith("/")
    || value.startsWith("//")
    || UNSAFE_RETURN_PATH_CHARACTERS.test(value)
  ) return "/";

  try {
    const destination = new URL(value, RETURN_PATH_ORIGIN);
    if (
      destination.origin !== RETURN_PATH_ORIGIN
      || !destination.pathname.startsWith("/")
      || destination.pathname.startsWith("//")
    ) return "/";
    return `${destination.pathname}${destination.search}${destination.hash}`;
  } catch {
    return "/";
  }
}

export function loginHref(returnTo: string) {
  return `/login?return_to=${encodeURIComponent(safeReturnPath(returnTo))}`;
}

export function locationReturnPath(location: {
  pathname: string;
  search: string;
}) {
  return safeReturnPath(`${location.pathname}${location.search}`);
}
