import { createHash, timingSafeEqual } from "node:crypto";

export const DELETION_SESSION_COOKIE = "wod_account_deletion_session";

function digest(value: string) {
  return createHash("sha256").update(value).digest("hex");
}

function sameDigest(left: string, right: string) {
  return /^[a-f0-9]{64}$/.test(left) && /^[a-f0-9]{64}$/.test(right)
    && timingSafeEqual(Buffer.from(left, "hex"), Buffer.from(right, "hex"));
}

/** This marker only protects Cookie cleanup from crossing login sessions.
 * The canonical API, not this marker, authorizes account deletion. */
export function deletionSessionMarker(ticket: string, currentBearer: string) {
  return `${digest(ticket)}.${digest(currentBearer)}`;
}

export function deletionMarkerMatchesTicket(marker: string | undefined, ticket: string) {
  if (!marker || !ticket) return false;
  const parts = marker.split(".");
  return parts.length === 2 && sameDigest(parts[0], digest(ticket));
}

export function deletionMayClearSession(marker: string | undefined, ticket: string, currentBearer: string | undefined) {
  if (!currentBearer || !deletionMarkerMatchesTicket(marker, ticket)) return false;
  return sameDigest(marker!.split(".")[1], digest(currentBearer));
}
