export const accountDeletionMethods = {
  eligibility: "GET",
  verify: "POST",
  submit: "POST",
  status: "POST",
} as const;

export type AccountDeletionOperation = keyof typeof accountDeletionMethods;

export function accountDeletionProxyOptions(operation: AccountDeletionOperation, body: Record<string, unknown>) {
  if (operation === "eligibility") return { method: "GET", auth: true };
  if (operation === "verify") return { method: "POST", auth: true, body: { password: body.password } };
  // Receipt-bound endpoints must work after normal sessions have been revoked.
  // Never forward a bearer token, user id, password, or URL query to these calls.
  return {
    method: "POST",
    auth: false,
    body: operation === "submit" ? { ticket: body.ticket, confirm: body.confirm } : { ticket: body.ticket },
  };
}
