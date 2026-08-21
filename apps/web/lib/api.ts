/**
 * Web requests stay on the Next.js origin. The server-side BFF forwards them
 * to the canonical mobile backend without exposing its JWT to browser code.
 */
export const apiBaseUrl = "";

export type ApiErrorBody = {
  detail?: string;
  message?: string;
  error?: { code?: string; message?: string };
};

export class ApiError extends Error {
  constructor(message: string, public readonly code?: string, public readonly status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

export async function readApiError(response: Response) {
  try {
    const body = (await response.json()) as ApiErrorBody;
    return body.detail ?? body.message ?? body.error?.message ?? `请求失败 (${response.status})`;
  } catch {
    return `请求失败 (${response.status})`;
  }
}

export type AuthUser = {
  id: number;
  display_name: string;
  email: string | null;
  email_verified: boolean;
  role: "personal" | "supplier" | "admin";
};

export type DeviceSession = {
  id: string;
  device_name: string;
  ip_address: string;
  status: "active" | "revoked" | "expired";
  is_current: boolean;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  revoked_at: string | null;
  revoke_reason: string | null;
};

export type AccountSecurity = {
  account: { display_name: string; email: string | null; email_verified: boolean; role: string };
  sessions: DeviceSession[];
  session_ttl_days: number;
};

export type ApiEnvelope<T, M extends Record<string, unknown> = Record<string, unknown>> = {
  data: T;
  meta: M;
};

const publicEnvelopeCache = new Map<string, { expiresAt: number; value: ApiEnvelope<unknown> }>();
const publicEnvelopeRequests = new Map<string, Promise<ApiEnvelope<unknown>>>();

export async function apiEnvelopeRequest<T, M extends Record<string, unknown> = Record<string, unknown>>(
  path: string,
  init: RequestInit = {},
): Promise<ApiEnvelope<T, M>> {
  const headers = new Headers(init.headers);
  const method = (init.method || "GET").toUpperCase();
  const formBody = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (init.body && !formBody && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      credentials: "same-origin",
      cache: init.cache ?? "no-store",
      headers,
    });
  } catch {
    throw new Error("网络连接失败，请检查网络后重试");
  }
  if (!response.ok) {
    let body: ApiErrorBody = {};
    try { body = await response.json() as ApiErrorBody; } catch { /* handled below */ }
    const message = body.detail ?? body.message ?? body.error?.message ?? `请求失败 (${response.status})`;
    throw new ApiError(message, body.error?.code, response.status);
  }
  return await response.json() as ApiEnvelope<T, M>;
}

/** Browser-side short cache and in-flight request coalescing for public GET data. */
export function publicApiEnvelopeRequest<T, M extends Record<string, unknown> = Record<string, unknown>>(
  path: string,
  maxAgeMs = 30_000,
  force = false,
): Promise<ApiEnvelope<T, M>> {
  if (typeof window === "undefined") {
    return apiEnvelopeRequest<T, M>(path, { cache: "default" });
  }
  const cached = publicEnvelopeCache.get(path);
  if (!force && cached && cached.expiresAt > Date.now()) {
    return Promise.resolve(cached.value as ApiEnvelope<T, M>);
  }
  const active = publicEnvelopeRequests.get(path);
  if (active) return active as Promise<ApiEnvelope<T, M>>;
  const pending = apiEnvelopeRequest<T, M>(path, { cache: force ? "reload" : "default" })
    .then((value) => {
      publicEnvelopeCache.set(path, { expiresAt: Date.now() + maxAgeMs, value: value as ApiEnvelope<unknown> });
      return value;
    })
    .finally(() => {
      if (publicEnvelopeRequests.get(path) === pending) publicEnvelopeRequests.delete(path);
    });
  publicEnvelopeRequests.set(path, pending as Promise<ApiEnvelope<unknown>>);
  return pending;
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await apiEnvelopeRequest<T>(path, init)).data;
}

export function emailLogin(input: { email: string; password: string }) {
  return apiRequest<{ user: AuthUser }>("/api/v1/auth/email/login", { method: "POST", body: JSON.stringify(input) });
}

export function emailRegister(input: { name: string; email: string; password: string }) {
  return apiRequest<{ user: AuthUser }>("/api/v1/auth/email/register", { method: "POST", body: JSON.stringify(input) });
}

export function passwordLogin(input: { identifier: string; password: string }) {
  return apiRequest<{ user: AuthUser }>("/api/v1/auth/password/login", { method: "POST", body: JSON.stringify(input) });
}

export function getAuthCaptcha() {
  return apiRequest<{ key: string; image: string }>("/api/v1/auth/captcha");
}

export function passwordRegister(input: { display_name: string; identifier: string; password: string; captcha_key: string; captcha_code: string; invite_code?: string }) {
  return apiRequest<{ user: AuthUser }>("/api/v1/auth/password/register", { method: "POST", body: JSON.stringify(input) });
}

export function getKaiAuthConfig() {
  return apiRequest<{ configured: boolean; issuer: string; scopes: string[] }>("/api/v1/auth/kai/config");
}

export function exchangeKaiTicket(ticket: string) {
  return apiRequest<{ user: AuthUser; return_to: string }>("/api/v1/auth/kai/exchange", {
    method: "POST",
    body: JSON.stringify({ ticket }),
  });
}

export function kaiWebAuthorizationUrl(intent: "login" | "register", returnTo: string) {
  const query = new URLSearchParams({ intent, return_to: returnTo });
  return `${apiBaseUrl}/api/v1/auth/kai/start?${query.toString()}`;
}

export function requestPasswordReset(email: string) {
  return apiRequest<{ accepted: boolean }>("/api/v1/auth/email/password-reset/request", { method: "POST", body: JSON.stringify({ email }) });
}

export function confirmPasswordReset(token: string, password: string) {
  return apiRequest<{ reset: boolean }>("/api/v1/auth/email/password-reset/confirm", { method: "POST", body: JSON.stringify({ token, password }) });
}

export function resendEmailVerification() {
  return apiRequest<{ accepted: boolean; already_verified: boolean }>("/api/v1/auth/email/verification/resend", { method: "POST" });
}

export function confirmEmailVerification(token: string) {
  return apiRequest<{ verified: boolean }>("/api/v1/auth/email/verification/confirm", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export function getCurrentUser() {
  return apiRequest<{ user: AuthUser }>("/api/v1/auth/me");
}

export function logoutCurrentUser() {
  return apiRequest<{ logged_out: boolean }>("/api/v1/auth/logout", { method: "POST" });
}

export function getAccountSecurity() {
  return apiRequest<AccountSecurity>("/api/v1/account/security/sessions");
}

export function revokeDeviceSession(id: string) {
  return apiRequest<{ revoked: boolean; current_session_revoked: boolean }>(`/api/v1/account/security/sessions/${encodeURIComponent(id)}/revoke`, { method: "POST" });
}

export function revokeOtherSessions() {
  return apiRequest<{ revoked_count: number }>("/api/v1/account/security/sessions/revoke-others", { method: "POST" });
}

export function revokeAllSessions() {
  return apiRequest<{ revoked_count: number }>("/api/v1/account/security/sessions/revoke-all", { method: "POST" });
}

export function changeAccountPassword(currentPassword: string, newPassword: string) {
  return apiRequest<{ changed: boolean; revoked_other_sessions: number }>("/api/v1/account/security/password", { method: "POST", body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) });
}
