type BinaryFetcher = (input: string | URL, init?: RequestInit) => Promise<Response>;

export type AuthenticatedBinaryProxyResult =
  | { ok: true; response: Response }
  | { ok: false; status: number; unavailable: boolean };

const receiptMimeExtensions = [
  ["image/jpeg", "jpg"],
  ["image/png", "png"],
  ["application/pdf", "pdf"],
] as const;

const downloadExtensionByContentType = new Map<string, string>(receiptMimeExtensions);

async function rejectUpstream(upstream: Response, status: number): Promise<AuthenticatedBinaryProxyResult> {
  try {
    await upstream.body?.cancel();
  } catch {
    // The safe rejection remains authoritative even when the upstream stream cannot be cancelled.
  }
  return { ok: false, status, unavailable: false };
}

export async function proxyAuthenticatedBinary(input: {
  url: string;
  token: string;
  accept: string;
  allowedContentTypes: readonly string[];
  downloadId: number;
  timeoutMs?: number;
  fetcher?: BinaryFetcher;
}): Promise<AuthenticatedBinaryProxyResult> {
  const fetcher = input.fetcher ?? fetch;
  let upstream: Response;
  try {
    upstream = await fetcher(input.url, {
      headers: {
        Accept: input.accept,
        Authorization: `Bearer ${input.token}`,
      },
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(input.timeoutMs ?? 20_000),
    });
  } catch {
    return { ok: false, status: 503, unavailable: true };
  }
  if (!upstream.ok) {
    const status = upstream.status >= 300 && upstream.status < 400 ? 502 : upstream.status;
    return rejectUpstream(upstream, status);
  }
  if (upstream.status !== 200 || !upstream.body) return rejectUpstream(upstream, 502);

  const upstreamContentType = upstream.headers.get("content-type");
  const contentType = upstreamContentType?.split(";", 1)[0].trim().toLowerCase();
  const extension = contentType ? downloadExtensionByContentType.get(contentType) : undefined;
  if (!contentType || !extension || !input.allowedContentTypes.includes(contentType)) return rejectUpstream(upstream, 502);
  if (!Number.isSafeInteger(input.downloadId) || input.downloadId <= 0) return rejectUpstream(upstream, 502);

  const headers = new Headers({ "Content-Type": contentType });
  headers.set("Content-Disposition", `attachment; filename="withdrawal-receipt-${input.downloadId}.${extension}"`);
  headers.set("Cache-Control", "private, no-store, max-age=0");
  headers.set("Pragma", "no-cache");
  headers.set("Expires", "0");
  headers.set("Referrer-Policy", "no-referrer");
  headers.set("Content-Security-Policy", "default-src 'none'; sandbox");
  headers.set("Cross-Origin-Resource-Policy", "same-origin");
  headers.set("X-Content-Type-Options", "nosniff");

  return {
    ok: true,
    response: new Response(upstream.body, { status: upstream.status, headers }),
  };
}
