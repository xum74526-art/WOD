import "server-only";

import type { NextRequest } from "next/server";

import { resolveApiOrigin } from "@/lib/server/api-origin";

export const WEB_TOKEN_COOKIE = "wod_web_token";
const WEB_LOCALE_COOKIE = "kai.locale";

export type CanonicalEnvelope = {
  code?: number;
  msg?: string;
  data?: unknown;
  detail?: unknown;
};

export type CanonicalApiResult = {
  ok: boolean;
  status: number;
  body: CanonicalEnvelope;
  response: Response;
};

type RequestOptions = {
  method?: string;
  body?: unknown;
  query?: URLSearchParams;
  auth?: boolean;
  revalidate?: number;
};

function envelope(value: unknown): CanonicalEnvelope {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as CanonicalEnvelope
    : {};
}

async function parseEnvelope(response: Response) {
  try {
    return envelope(await response.json());
  } catch {
    return {};
  }
}

function unavailable(message: string): CanonicalApiResult {
  return {
    ok: false,
    status: 503,
    body: { code: 1, msg: message },
    response: new Response(null, { status: 503 }),
  };
}

function authHeaders(request: NextRequest, auth = true) {
  const headers = new Headers({ Accept: "application/json" });
  const locale = request.cookies.get(WEB_LOCALE_COOKIE)?.value;
  headers.set(
    "Accept-Language",
    locale === "en" ? "en-US,en;q=0.9" : locale === "zh-Hans" ? "zh-CN,zh;q=0.9" : "zh-TW,zh-Hant;q=0.9,zh;q=0.8",
  );
  const token = request.cookies.get(WEB_TOKEN_COOKIE)?.value;
  if (auth && token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

export async function callCanonicalApi(
  request: NextRequest,
  path: string,
  options: RequestOptions = {},
): Promise<CanonicalApiResult> {
  const headers = authHeaders(request, options.auth !== false);
  const body = options.body === undefined ? undefined : JSON.stringify(options.body);
  if (body !== undefined) headers.set("Content-Type", "application/json");
  const query = options.query?.toString();
  const method = options.method || request.method;
  const cacheable = options.auth === false && method === "GET" && typeof options.revalidate === "number" && options.revalidate > 0;
  let response: Response;
  try {
    response = await fetch(`${resolveApiOrigin()}${path}${query ? `?${query}` : ""}`, {
      method,
      headers,
      body,
      cache: cacheable ? "force-cache" : "no-store",
      ...(cacheable ? { next: { revalidate: options.revalidate } } : {}),
      redirect: "manual",
      signal: AbortSignal.timeout(15_000),
    });
  } catch (error) {
    return unavailable(
      error instanceof Error && error.name === "TimeoutError"
        ? "业务服务响应超时"
        : "暂时无法连接业务服务，请稍后重试",
    );
  }
  const parsed = await parseEnvelope(response);
  return { ok: response.ok && parsed.code !== 1, status: response.status, body: parsed, response };
}

export async function callCanonicalMultipart(
  request: NextRequest,
  path: string,
  fileFields: string[],
  failureMessage: string,
  textFields: string[] = [],
  timeoutMs: number = 60_000,
): Promise<CanonicalApiResult> {
  const headers = authHeaders(request);
  const incoming = await request.formData();
  const outgoing = new FormData();
  for (const field of fileFields) {
    const file = incoming.get(field);
    if (file instanceof File && file.size > 0) outgoing.set(field, file, file.name);
  }
  for (const field of textFields) {
    const value = incoming.get(field);
    if (typeof value === "string") outgoing.set(field, value);
  }

  let response: Response;
  try {
    response = await fetch(`${resolveApiOrigin()}${path}`, {
      method: "POST",
      headers,
      body: outgoing,
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch {
    return unavailable(failureMessage);
  }
  const parsed = await parseEnvelope(response);
  return { ok: response.ok && parsed.code !== 1, status: response.status, body: parsed, response };
}

export function canonicalErrorMessage(result: CanonicalApiResult) {
  const detail = result.body.detail;
  if (result.body.msg) return result.body.msg;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map(item => item && typeof item === "object" ? String((item as { msg?: unknown }).msg || "") : "")
      .filter(Boolean);
    if (messages.length) return messages.join("；");
  }
  return `业务服务请求失败 (${result.status})`;
}
