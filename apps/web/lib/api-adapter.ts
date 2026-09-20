import "server-only";

import { NextRequest, NextResponse } from "next/server";
import { normalizeStoredLocale } from "@/lib/language";
import { isValidMarketLatestPayload } from "@/lib/market-latest-payload";
import { notificationActionPath } from "@/lib/notification-navigation";
import { createStaleTtlCache } from "@/lib/stale-ttl-cache";
import { resolveApiOrigin } from "@/lib/server/api-origin";
import {
  allowedPaymentCheckoutRedirect,
  paymentCheckoutAllowedHosts,
  paymentCheckoutClientIp,
} from "@/lib/server/payment-checkout-policy";
import { accountDeletionMethods, accountDeletionProxyOptions, type AccountDeletionOperation } from "@/lib/account-deletion-proxy";
import { deletionRevokesNormalSession } from "@/lib/account-deletion-flow";
import { safeReturnPath } from "@/lib/auth-navigation";
import { DELETION_SESSION_COOKIE, deletionMarkerMatchesTicket, deletionMayClearSession, deletionSessionMarker } from "@/lib/server/account-deletion-session";
import { proxyAuthenticatedBinary } from "@/lib/server/authenticated-binary-proxy";
import { PAYOUT_RECEIPT_ACCEPT, PAYOUT_RECEIPT_MIME_TYPES } from "@/lib/payout-receipt";
import {
  readBoundedJsonBody,
  REGISTRATION_BODY_MAX_BYTES,
  REGISTRATION_BODY_TOO_LARGE_MESSAGE,
  RequestBodyTooLargeError,
} from "@/lib/server/bounded-json-body";
import {
  callCanonicalApi as upstream,
  callCanonicalMultipart as upstreamMultipart,
  canonicalErrorMessage,
  type CanonicalApiResult,
  WEB_TOKEN_COOKIE as TOKEN_COOKIE,
} from "@/lib/server/canonical-api-client";

const RETURN_TO_COOKIE = "wod_web_return_to";

type JsonObject = Record<string, unknown>;

type PublicMarketSummaryPayload = {
  data: JsonObject[];
  meta: JsonObject;
  complete: boolean;
};

type PublicMarketLatestPayload = {
  data: JsonObject;
};

const PUBLIC_MARKET_SUMMARY_TTL_MS = 300_000;
const PUBLIC_MARKET_SUMMARY_STALE_MS = 600_000;
const PUBLIC_MARKET_SUMMARY_RETRY_DELAY_MS = 5_000;
const PUBLIC_MARKET_SUMMARY_CACHE_LIMIT = 8;
const PUBLIC_MARKET_LATEST_TTL_MS = 300_000;
const PUBLIC_MARKET_LATEST_STALE_MS = 600_000;
const PUBLIC_MARKET_LATEST_RETRY_DELAY_MS = 2_000;
const PUBLIC_MARKET_LATEST_CACHE_LIMIT = 256;

class PublicMarketSummaryUpstreamError extends Error {
  constructor(readonly result: CanonicalApiResult) {
    super(canonicalErrorMessage(result));
    this.name = "PublicMarketSummaryUpstreamError";
  }
}

class PublicMarketLatestUpstreamError extends Error {
  constructor(readonly result: CanonicalApiResult) {
    super(canonicalErrorMessage(result));
    this.name = "PublicMarketLatestUpstreamError";
  }
}

class PublicMarketLatestPayloadError extends Error {
  constructor() {
    super("实时行情返回数据异常");
    this.name = "PublicMarketLatestPayloadError";
  }
}

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
}

function array(value: unknown): JsonObject[] {
  return Array.isArray(value) ? value.map(object) : [];
}

async function mapWithConcurrency<T, R>(items: T[], concurrency: number, mapper: (item: T) => Promise<R>): Promise<R[]> {
  const results = new Array<R>(items.length);
  let cursor = 0;
  async function worker() {
    while (cursor < items.length) {
      const index = cursor++;
      results[index] = await mapper(items[index]);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, worker));
  return results;
}

function text(value: unknown, fallback = "") {
  return typeof value === "string" ? value : value == null ? fallback : String(value);
}

function number(value: unknown, fallback = 0) {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}

function apiError(message: string, status = 400, code = "mobile_backend_error") {
  return NextResponse.json({ error: { code, message } }, {
    status,
    headers: { "Cache-Control": "private, no-store" },
  });
}

function apiSuccess(data: unknown, meta: JsonObject = {}, status = 200) {
  return NextResponse.json({ data, meta }, {
    status,
    headers: { "Cache-Control": "private, no-store" },
  });
}

function publicApiSuccess(data: unknown, meta: JsonObject = {}, maxAge = 10) {
  return NextResponse.json({ data, meta }, {
    headers: {
      "Cache-Control": `public, max-age=${maxAge}, s-maxage=${Math.max(maxAge, 30)}, stale-while-revalidate=120`,
    },
  });
}

function publicRealtimeApiSuccess(data: unknown, meta: JsonObject = {}) {
  return NextResponse.json({ data, meta }, {
    headers: { "Cache-Control": "private, no-store" },
  });
}

function isMutation(method: string) {
  return !["GET", "HEAD", "OPTIONS"].includes(method);
}

function sameOrigin(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  try {
    const requestHost = request.headers.get("x-forwarded-host") || request.headers.get("host") || request.nextUrl.host;
    return new URL(origin).host === requestHost;
  } catch {
    return false;
  }
}

async function requestBody(request: NextRequest, maxBytes?: number): Promise<JsonObject> {
  if (!isMutation(request.method)) return {};
  const contentType = request.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) return {};
  try {
    return object(maxBytes === undefined
      ? await request.json()
      : await readBoundedJsonBody(request, maxBytes));
  } catch (error) {
    if (error instanceof RequestBodyTooLargeError) throw error;
    return {};
  }
}

function upstreamFailure(result: CanonicalApiResult) {
  return apiError(canonicalErrorMessage(result), result.status || 502);
}

function recoveryApiResponse(result: CanonicalApiResult) {
  const response = result.ok
    ? apiSuccess(result.body.data, { source: "canonical-api" })
    : upstreamFailure(result);
  response.headers.set("Cache-Control", "private, no-store");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}

function authUser(value: unknown) {
  const user = object(value);
  const role = ["personal", "supplier", "admin"].includes(text(user.role))
    ? text(user.role) as "personal" | "supplier" | "admin"
    : "personal";
  return {
    id: number(user.id),
    display_name: text(user.username, `用户${number(user.id)}`),
    email: null,
    email_verified: false,
    phone: text(user.phone) || null,
    phone_bound: Boolean(user.phone_bound),
    avatar: text(user.avatar) || null,
    role,
    supplier_status: text(user.supplier_status, "not_applied"),
  };
}

function requestIsHttps(request: NextRequest) {
  return (request.headers.get("x-forwarded-proto") || request.nextUrl.protocol.replace(":", "")) === "https";
}

function setAuthCookie(request: NextRequest, response: NextResponse, token: string) {
  response.cookies.set(TOKEN_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: requestIsHttps(request),
    path: "/",
    maxAge: 60 * 120,
  });
}

function clearAuthCookie(request: NextRequest, response: NextResponse) {
  response.cookies.set(TOKEN_COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: requestIsHttps(request),
    path: "/",
    maxAge: 0,
  });
}

function publicOrigin(request: NextRequest) {
  const configured = process.env.WEB_PUBLIC_ORIGIN?.trim();
  if (configured) {
    const url = new URL(configured);
    if (url.username || url.password || url.search || url.hash || (url.pathname !== "/" && url.pathname !== "")) {
      throw new Error("WEB_PUBLIC_ORIGIN must contain only the public Web origin");
    }
    if (process.env.NODE_ENV === "production" && url.protocol !== "https:") {
      throw new Error("WEB_PUBLIC_ORIGIN must use HTTPS in production");
    }
    return url.origin;
  }
  const protocol = request.headers.get("x-forwarded-proto") || request.nextUrl.protocol.replace(":", "");
  const host = request.headers.get("x-forwarded-host") || request.headers.get("host") || request.nextUrl.host;
  return new URL(`${protocol}://${host}`).origin;
}

async function proxyAvatar(request: NextRequest, filename: string) {
  if (!/^avatar_\d+\.(?:jpg|png|webp)$/.test(filename)) return apiError("头像不存在", 404);
  const query = request.nextUrl.searchParams.toString();
  let response: Response;
  try {
    response = await fetch(`${resolveApiOrigin()}/api/user/avatars/${filename}${query ? `?${query}` : ""}`, {
      headers: { Accept: "image/avif,image/webp,image/png,image/jpeg" },
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    return apiError("头像暂时无法读取", 503);
  }
  if (!response.ok) return apiError("头像不存在", response.status);
  return new NextResponse(response.body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") || "application/octet-stream",
      "Cache-Control": "private, max-age=300",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

async function proxyCommunityMedia(request: NextRequest, userId: string, filename: string) {
  if (!/^[1-9]\d*$/.test(userId) || !/^[0-9a-f]{32}\.(?:jpg|png|webp|mp4|mov|webm)$/.test(filename)) return apiError("社区媒体不存在", 404);
  const headers = new Headers({ Accept: request.headers.get("accept") || "*/*" });
  const range = request.headers.get("range");
  if (range) headers.set("Range", range);
  let response: Response;
  try { response = await fetch(`${resolveApiOrigin()}/api/uploads/community/${userId}/${filename}`, { headers, cache: "no-store", signal: AbortSignal.timeout(30_000) }); }
  catch { return apiError("社区媒体暂时无法读取", 503); }
  if (!response.ok && response.status !== 206) return apiError("社区媒体不存在", response.status);
  const outgoing = new Headers({ "Content-Type": response.headers.get("content-type") || "application/octet-stream", "Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff" });
  for (const name of ["accept-ranges", "content-range", "content-length"]) { const value = response.headers.get(name); if (value) outgoing.set(name, value); }
  return new NextResponse(response.body, { status: response.status, headers: outgoing });
}

async function proxyWithdrawalReceipt(request: NextRequest, orderId: string) {
  const token = request.cookies.get(TOKEN_COOKIE)?.value;
  if (!token) return apiError("未登录", 401);
  const result = await proxyAuthenticatedBinary({
    url: `${resolveApiOrigin()}/api/finance/withdrawals/${orderId}/receipt`,
    token,
    accept: PAYOUT_RECEIPT_ACCEPT,
    allowedContentTypes: PAYOUT_RECEIPT_MIME_TYPES,
    downloadId: Number(orderId),
  });
  if (!result.ok) {
    return apiError(result.unavailable ? "打款凭证暂时无法读取" : "打款凭证无法读取", result.status);
  }
  return result.response;
}

async function proxyCheckout(request: NextRequest, provider: "mapay" | "qixiang", token: string) {
  if (provider !== "qixiang") {
    return apiError("旧支付链接已停用，请返回钱包重新发起充值", 410, "legacy_checkout_disabled");
  }
  let response: Response;
  try {
    const headers = new Headers({ Accept: "application/json" });
    const clientIp = paymentCheckoutClientIp(request.headers);
    if (clientIp) headers.set("X-Real-IP", clientIp);
    response = await fetch(`${resolveApiOrigin()}/api/payments/${provider}/checkout/${encodeURIComponent(token)}`, {
      headers,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    return new NextResponse("支付页面暂时无法打开", { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } });
  }
  const location = response.headers.get("location");
  if (response.status === 303 && location) {
    const destination = allowedPaymentCheckoutRedirect(location, paymentCheckoutAllowedHosts());
    if (!destination) {
      return apiError("支付平台返回了无效收银台地址", 502);
    }
    const redirect = NextResponse.redirect(destination, 303);
    redirect.headers.set("Cache-Control", "private, no-store");
    redirect.headers.set("Referrer-Policy", "no-referrer");
    redirect.headers.set("X-Content-Type-Options", "nosniff");
    return redirect;
  }
  const status = response.status >= 400 && response.status < 500 ? response.status : 502;
  return apiError("支付页面暂时无法打开，请返回钱包查询订单状态", status, "checkout_unavailable");
}

function product(value: unknown) {
  const item = object(value);
  const rawSupplierId = item.supplier_id == null ? null : number(item.supplier_id);
  const rawMarketSource = text(item.market_source).toLowerCase();
  const rawSellerType = text(item.seller_type).toLowerCase();
  const legacyMerchant = rawSellerType === "merchant"
    || text(item.fulfillment_mode).toLowerCase() === "merchant_manual"
    || text(item.resource_claim_source).toLowerCase() === "merchant_declared"
    || (rawSupplierId != null && rawSupplierId > 0);
  const marketSource = rawMarketSource === "kai" || rawMarketSource === "wod"
    ? rawMarketSource
    : legacyMerchant ? "wod" : "kai";
  const sellerType = rawSellerType === "merchant" || (rawSellerType !== "kai_self_operated" && marketSource === "wod")
    ? "merchant"
    : "kai_self_operated";
  const supplierId = sellerType === "merchant" && rawSupplierId != null && rawSupplierId > 0 ? rawSupplierId : null;
  const supplierName = text(item.supplier_name) || null;
  const sellerName = text(item.seller_name) || supplierName || (sellerType === "kai_self_operated" ? "算力星图自营" : "第三方商家");
  const fulfillmentMode = text(
    item.fulfillment_mode,
    sellerType === "kai_self_operated" ? "platform_manual" : "merchant_manual",
  ) === "merchant_manual" ? "merchant_manual" : "platform_manual";
  const resourceClaimSource = text(
    item.resource_claim_source,
    sellerType === "kai_self_operated" ? "kai_published" : "merchant_declared",
  ) === "merchant_declared" ? "merchant_declared" : "kai_published";
  const memory = text(item.memory);
  const memoryGb = number(memory.match(/\d+(?:\.\d+)?/)?.[0]);
  const price = number(item.price_cny_per_gpu_hour, number(item.price));
  const walletPrice = number(item.price_card_hours_per_gpu_hour, price);
  const stock = number(item.stock);
  // KAI and merchant listings share the same hourly purchase contract.  Older
  // API deployments may omit this newly-added field, so the compatibility
  // fallback must not silently turn merchant products back into day products.
  const purchaseUnit = text(item.purchase_unit, "hour");
  const hourOptions = Array.isArray(item.purchase_hour_options)
    ? item.purchase_hour_options.map((entry) => number(entry)).filter((entry) => Number.isInteger(entry) && entry > 0)
    : [];
  return {
    id: number(item.id),
    supplier_id: supplierId,
    supplier_name: supplierName,
    supplier_rating: item.supplier_rating == null ? null : number(item.supplier_rating),
    supplier_order_count: item.supplier_order_count == null ? null : number(item.supplier_order_count),
    seller_type: sellerType,
    seller_name: sellerName,
    fulfillment_mode: fulfillmentMode,
    resource_claim_source: resourceClaimSource,
    assurance_label: text(item.assurance_label, sellerType === "kai_self_operated" ? "算力星图自营 · 平台人工交付" : "商家发布 · 商家人工交付"),
    assurance_description: text(
      item.assurance_description,
      sellerType === "kai_self_operated"
        ? "价格与商品由算力星图发布，平台安排人工交付。"
        : "商品配置与库存由商家自行申报，并由该商家负责人工交付；平台记录订单、验收与争议状态。",
    ),
    name: text(item.name),
    gpu_model: text(item.gpu_model),
    memory,
    gpu_memory_gb: memoryGb,
    region: text(item.region_name, text(item.region_code, text(item.city, "地区待确认"))),
    description: text(item.desc),
    cpu_cores: null,
    ram_gb: null,
    disk_gb: null,
    bandwidth_mbps: null,
    unit_price_ch: walletPrice,
    price: { amount: price.toFixed(4), currency: "CNY", unit: "GPU·小时" },
    total_quantity: item.reported_stock == null ? stock : number(item.reported_stock, stock),
    available_quantity: stock,
    source_name: supplierName || (sellerType === "kai_self_operated" ? "KAI Pricing" : sellerName),
    source_observed_at: text(item.price_updated_at) || null,
    inquiry_available: item.inquiry_available !== false,
    interaction_mode: ["direct_trade", "matchmaking", "history_only"].includes(text(item.interaction_mode))
      ? text(item.interaction_mode)
      : Boolean(item.purchasable) ? "direct_trade" : "matchmaking",
    purchasable: Boolean(item.purchasable),
    purchase_unavailable_reason: text(item.purchase_unavailable_reason) || null,
    cycle: Array.isArray(item.cycle) ? item.cycle.map((entry) => number(entry)).filter(Boolean) : [],
    purchase_unit: purchaseUnit,
    purchase_hour_options: hourOptions,
    billing_unit: text(item.billing_unit, "GPU_HOUR"),
    image_url: text(item.image_url) || null,
    market_source: marketSource,
  };
}

function pageEnvelope(value: unknown) {
  const page = object(value);
  const items = Array.isArray(page.items) ? page.items : [];
  const current = number(page.page, 1);
  const size = number(page.page_size, Math.max(items.length, 1));
  const total = number(page.total, items.length);
  const totalPages = number(page.total_pages, Math.max(1, Math.ceil(total / size)));
  return {
    data: items,
    meta: { page: current, page_size: size, total, total_pages: totalPages },
  };
}

function address(value: unknown) {
  const item = object(value);
  return {
    id: number(item.id),
    label: text(item.label, "常用地址"),
    recipient_name: text(item.name),
    phone: text(item.phone),
    country_code: "CN",
    province: text(item.province),
    city: text(item.city),
    district: text(item.district) || null,
    address_line: text(item.detail),
    postal_code: null,
    is_default: Boolean(item.is_default),
    created_at: text(item.created_at),
    updated_at: text(item.created_at),
    version: 1,
  };
}

function notice(value: unknown) {
  const item = object(value);
  return {
    id: number(item.id),
    category: text(item.type, "system"),
    title: text(item.title),
    body: text(item.content),
    action_path: notificationActionPath(item.action_url),
    is_read: Boolean(item.is_read),
    read_at: null,
    created_at: text(item.created_at),
  };
}

function order(value: unknown, supplierView = false) {
  const item = object(value);
  const productSnapshot = object(item.product_snapshot);
  const cycleDays = item.cycle_days == null ? null : number(item.cycle_days);
  const purchaseHours = item.purchase_hours == null
    ? (item.purchase_unit === "hour" && item.duration_hours != null ? number(item.duration_hours) : null)
    : number(item.purchase_hours);
  const canonicalStatus = text(item.status);
  const supplierName = text(item.supplier_name, "算力星图商家");
  const sellerType = text(item.seller_type, text(item.market_source) === "kai" ? "kai_self_operated" : "merchant") === "kai_self_operated"
    ? "kai_self_operated"
    : "merchant";
  const sellerName = text(item.seller_name, supplierName);
  const fulfillmentMode = text(item.fulfillment_mode, sellerType === "kai_self_operated" ? "platform_manual" : "merchant_manual") === "platform_manual"
    ? "platform_manual"
    : "merchant_manual";
  const available: string[] = [];
  // Buyer mutations are advertised by FastAPI after ownership and state
  // checks. The BFF must not recreate a second order state machine.
  if (!supplierView && Boolean(item.can_confirm)) available.push("complete");
  if (!supplierView && Boolean(item.can_cancel)) available.push("cancel");
  if (!supplierView && Boolean(item.can_dispute)) available.push("dispute");
  if (!supplierView && Boolean(item.can_renew)) available.push("renew");
  // FastAPI owns delivery authorization. The paid-state branch only protects
  // older deployed API versions that do not expose can_deliver yet.
  if (supplierView && (Boolean(item.can_deliver) || (item.can_deliver == null && item.status === "paid"))) available.push("mark_delivered");
  return {
    id: number(item.id),
    order_no: text(item.order_no),
    status: canonicalStatus,
    buyer_id: number(item.user_id),
    supplier_id: number(item.supplier_id),
    buy_request_id: null,
    accepted_quote_id: null,
    product_id: number(item.product_id),
    order_source: "direct",
    environment: "live",
    payment_status: ["paid", "delivering", "completed", "running"].includes(text(item.status)) ? "paid" : "pending",
    duration_hours: purchaseHours ?? (cycleDays == null ? null : cycleDays * 24),
    purchase_hours: purchaseHours,
    amount: number(item.amount_card_hours, number(item.amount)).toFixed(4),
    currency: "CARD_HOURS",
    price_unit: "order_total",
    quantity: number(item.quantity, 1),
    purchase_type: text(item.purchase_type, "usage"),
    market_source: text(item.market_source) === "kai" ? "kai" : text(item.market_source) === "wod" ? "wod" : null,
    cycle_days: cycleDays,
    end_at: text(item.end_at) || null,
    remaining_days: number(item.remaining_days),
    remaining_hours: item.remaining_hours == null ? null : number(item.remaining_hours),
    created_platform: text(item.created_platform, "legacy"),
    last_modified_platform: text(item.last_modified_platform, "legacy"),
    snapshot: {
      payment_mode: "mobile_wallet",
      product: {
        resource_no: `WOD-P-${number(item.product_id)}`,
        name: text(productSnapshot.product_name, text(item.product_name, "算力资源")),
        gpu_model: text(productSnapshot.gpu_model, text(item.gpu_model)),
        region: text(productSnapshot.region_name, text(productSnapshot.region_code, text(productSnapshot.city))),
        unit_price: text(productSnapshot.confirmed_unit_price_card_hours),
      },
    },
    buyer_confirmed_at: text(item.confirmed_at) || null,
    supplier_confirmed_at: null,
    confirmed_at: text(item.confirmed_at) || null,
    delivery_started_at: null,
    delivered_at: text(item.delivered_at) || null,
    completed_at: text(item.confirmed_at) || null,
    cancelled_at: text(item.canceled_at) || null,
    cancel_reason: null,
    delivery_note: text(item.ssh_info) || null,
    fulfillment_status: text(item.fulfillment_status) || null,
    seller_type: sellerType,
    seller_name: sellerName,
    fulfillment_mode: fulfillmentMode,
    delivery_due_at: text(item.delivery_due_at) || null,
    confirmation_due_at: text(item.confirmation_due_at) || null,
    disputed_at: text(item.disputed_at) || null,
    dispute_due_at: text(item.dispute_due_at) || null,
    dispute_reason: text(item.dispute_reason) || null,
    dispute_resolution: text(item.dispute_resolution) || null,
    dispute_resolution_note: text(item.dispute_resolution_note) || null,
    dispute_resolved_at: text(item.dispute_resolved_at) || null,
    created_at: text(item.created_at),
    updated_at: text(item.created_at),
    version: 1,
    buyer: { display_name: text(item.buyer_name, "买家") },
    supplier: { display_name: sellerName, company_name: sellerName },
    available_actions: available,
    events: [],
  };
}

function modelMemory(model: string, variant: string) {
  const matched = `${variant} ${model}`.match(/(?:^|\D)(\d{2,3})\s*(?:GB|G)(?:\D|$)/i);
  return matched ? number(matched[1]) : undefined;
}

function publicMarketLocale(request: NextRequest) {
  return normalizeStoredLocale(request.cookies.get("kai.locale")?.value);
}

function publicMarketLatestQuery(searchParams: URLSearchParams) {
  const models = searchParams.getAll("model");
  const variants = searchParams.getAll("variant");
  const sources = searchParams.getAll("sources");
  if (models.length !== 1 || variants.length > 1 || sources.length > 1) return null;

  const model = models[0].trim();
  const variant = variants[0]?.trim() ?? "";
  const source = sources[0]?.trim().toLowerCase() || "kai";
  if (!model || source !== "kai") return null;

  const query = new URLSearchParams({ model, sources: "kai" });
  if (variant) query.set("variant", variant);
  return query;
}

async function marketRanking(request: NextRequest) {
  const ranking = await upstream(request, "/api/market/ranking", { auth: false, revalidate: 300 });
  if (!ranking.ok) return upstreamFailure(ranking);
  const rankingData = object(ranking.body.data);
  const entries = array(rankingData.items).map((entry) => ({
    gpu_model: text(entry.gpu_model),
    gpu_variant: text(entry.gpu_variant),
    median_price_cny: number(entry.median_price_cny),
    median_price_card_hours: number(entry.median_price_card_hours),
    change_24h: number(entry.change_24h),
    available_gpu_count: number(entry.available_gpu_count),
    source_count: number(entry.source_count),
    sources: Array.isArray(entry.sources) ? entry.sources.map((source) => text(source)).filter(Boolean) : [],
    history_day_count: number(entry.history_day_count),
    history_point_count: number(entry.history_point_count),
    market_status: text(entry.market_status),
  }));
  return publicApiSuccess(entries, {
    observed_at: text(rankingData.server_time),
    count: entries.length,
    source: "canonical-api",
  }, 300);
}

async function buildMarketSummary(request: NextRequest): Promise<PublicMarketSummaryPayload> {
  const ranking = await upstream(request, "/api/market/ranking", { auth: false });
  if (!ranking.ok) throw new PublicMarketSummaryUpstreamError(ranking);
  const rankingData = object(ranking.body.data);
  const entries = array(rankingData.items);
  let complete = entries.length > 0;
  const withHistory = await mapWithConcurrency(entries, 8, async (entry) => {
    const model = text(entry.gpu_model);
    const variant = text(entry.gpu_variant);
    const query = new URLSearchParams({ model, range: "90d", sources: "kai", billing_mode: "ondemand" });
    if (variant) query.set("variant", variant);
    const candleResult = await upstream(request, "/api/market/prices/candles", { query, auth: false });
    const candleData = candleResult.ok ? object(candleResult.body.data) : {};
    const candleRows = array(candleData.candles);
    if (
      !candleResult.ok
      || !Array.isArray(candleData.candles)
      || text(candleData.gpu_model) !== model
      || text(candleData.gpu_variant) !== variant
      || text(candleData.range) !== "90d"
    ) complete = false;
    const history = candleRows
      .map((candle) => ({
        date: text(candle.start_time).slice(0, 10),
        median: number(candle.close_price_card_hours, NaN),
      }))
      .filter((point) => point.date && Number.isFinite(point.median) && point.median > 0)
      .sort((a, b) => b.date.localeCompare(a.date));
    if (history.length !== candleRows.length) complete = false;
    const current = number(entry.median_price_card_hours);
    return {
      gpu_model: variant ? `${model} ${variant}`.trim() : model,
      tier: text(entry.market_status),
      vram_gb: modelMemory(model, variant),
      min_price: current,
      median_price: current,
      official_min_price: current,
      official_median_price: current,
      history,
      has_current_offers: number(entry.available_gpu_count) > 0,
      offer_count: number(entry.available_gpu_count),
      provider_count: number(entry.source_count),
      gpu_count: number(entry.available_gpu_count),
      representative_offer_id: null,
      region: "多区域",
      reliability: text(entry.market_status) === "live" ? 100 : 0,
    };
  });
  return {
    data: withHistory,
    meta: {
      observed_at: text(rankingData.server_time),
      history_updated_at: text(rankingData.server_time),
      count: withHistory.length,
      source: "canonical-api",
    },
    complete,
  };
}

const readPublicMarketSummary = createStaleTtlCache<
  [NextRequest, string, string],
  PublicMarketSummaryPayload
>({
  key: (_request, apiOrigin, locale) => JSON.stringify([apiOrigin, locale]),
  load: (request) => buildMarketSummary(request),
  ttlMs: PUBLIC_MARKET_SUMMARY_TTL_MS,
  maxEntries: PUBLIC_MARKET_SUMMARY_CACHE_LIMIT,
  staleMs: PUBLIC_MARKET_SUMMARY_STALE_MS,
  retryDelayMs: PUBLIC_MARKET_SUMMARY_RETRY_DELAY_MS,
  shouldStore: (payload) => payload.complete,
});

async function marketSummary(request: NextRequest) {
  try {
    const payload = await readPublicMarketSummary(request, resolveApiOrigin(), publicMarketLocale(request));
    return publicApiSuccess(payload.data, payload.meta, 300);
  } catch (error) {
    if (error instanceof PublicMarketSummaryUpstreamError) return upstreamFailure(error.result);
    return apiError("市场行情暂时不可用，请稍后重试", 503);
  }
}

async function buildPublicMarketLatest(request: NextRequest, queryString: string): Promise<PublicMarketLatestPayload> {
  const query = new URLSearchParams(queryString);
  const result = await upstream(request, "/api/market/prices/latest", {
    query,
    auth: false,
  });
  if (!result.ok) throw new PublicMarketLatestUpstreamError(result);
  if (
    result.body.code !== 0
    || !isValidMarketLatestPayload(result.body.data, {
      model: query.get("model") ?? "",
      variant: query.has("variant") ? query.get("variant") : null,
    })
  ) throw new PublicMarketLatestPayloadError();
  return { data: result.body.data };
}

const readPublicMarketLatest = createStaleTtlCache<
  [NextRequest, string, string, string],
  PublicMarketLatestPayload
>({
  key: (_request, apiOrigin, locale, queryString) => JSON.stringify([apiOrigin, locale, queryString]),
  load: (request, _apiOrigin, _locale, queryString) => buildPublicMarketLatest(request, queryString),
  ttlMs: PUBLIC_MARKET_LATEST_TTL_MS,
  maxEntries: PUBLIC_MARKET_LATEST_CACHE_LIMIT,
  staleMs: PUBLIC_MARKET_LATEST_STALE_MS,
  retryDelayMs: PUBLIC_MARKET_LATEST_RETRY_DELAY_MS,
  refreshMode: "blocking",
});

async function publicMarketLatest(request: NextRequest) {
  const query = publicMarketLatestQuery(request.nextUrl.searchParams);
  if (!query) return apiError("无效的实时行情查询参数", 400, "invalid_market_query");
  try {
    const payload = await readPublicMarketLatest(
      request,
      resolveApiOrigin(),
      publicMarketLocale(request),
      query.toString(),
    );
    return publicRealtimeApiSuccess(payload.data, { source: "canonical-api" });
  } catch (error) {
    if (error instanceof PublicMarketLatestUpstreamError) return upstreamFailure(error.result);
    if (error instanceof PublicMarketLatestPayloadError) {
      return apiError("实时行情返回数据异常，请稍后重试", 502, "invalid_market_payload");
    }
    return apiError("实时行情暂时不可用，请稍后重试", 503);
  }
}

async function accountSummary(request: NextRequest) {
  const [profileResult, ordersResult, assetsResult, walletResult, verificationResult] = await Promise.all([
    upstream(request, "/api/user/profile"),
    upstream(request, "/api/orders"),
    upstream(request, "/api/assets"),
    upstream(request, "/api/wallet"),
    upstream(request, "/api/verification"),
  ]);
  if (!profileResult.ok) return upstreamFailure(profileResult);
  const profile = authUser(profileResult.body.data);
  const orders = ordersResult.ok && Array.isArray(ordersResult.body.data) ? ordersResult.body.data : [];
  const assets = assetsResult.ok ? array(object(assetsResult.body.data).items) : [];
  const wallet = walletResult.ok ? object(walletResult.body.data) : {};
  const verification = verificationResult.ok ? object(verificationResult.body.data) : {};
  return apiSuccess({
    user: profile,
    metrics: {
      active_orders: orders.filter((item) => !["completed", "running", "canceled"].includes(text(object(item).status))).length,
      active_assets: assets.length,
      hosted_devices: 0,
      open_requests: 0,
    },
    supplier_status: profile.supplier_status,
    services: {
      payment: Boolean(wallet.payment_service_enabled || wallet.recharge_service_enabled),
      recharge: Boolean(wallet.recharge_service_enabled),
      withdraw: Boolean(wallet.withdraw_service_enabled),
      kyc: text(verification.status) === "verified",
    },
  });
}

function unavailable(path: string) {
  return apiError(`此 Web 模块没有可用业务数据源，已停用：${path}`, 503, "business_source_unavailable");
}

export async function handleApi(request: NextRequest, segments: string[]) {
  if (isMutation(request.method) && !sameOrigin(request)) return apiError("请求来源校验失败", 403, "origin_mismatch");
  const requestedPath = segments.join("/");
  // `/mobile/*` was the original BFF pass-through name. Normalize it at one
  // boundary so deployed bookmarks keep working while all current clients use
  // the platform-neutral `/canonical/*` contract.
  const path = requestedPath.startsWith("mobile/")
    ? `canonical/${requestedPath.slice("mobile/".length)}`
    : requestedPath;
  const checkout = path.match(/^canonical\/payments\/(mapay|qixiang)\/checkout\/([A-Za-z0-9_-]{32,128})$/);
  if (checkout && request.method === "GET") return proxyCheckout(request, checkout[1] as "mapay" | "qixiang", checkout[2]);
  const avatar = path.match(/^canonical\/user\/avatars\/(avatar_\d+\.(?:jpg|png|webp))$/);
  if (avatar && request.method === "GET") return proxyAvatar(request, avatar[1]);
  const communityMedia = path.match(/^canonical\/uploads\/community\/([1-9]\d*)\/([0-9a-f]{32}\.(?:jpg|png|webp|mp4|mov|webm))$/);
  if (communityMedia && request.method === "GET") return proxyCommunityMedia(request, communityMedia[1], communityMedia[2]);
  const verificationPhoto = path.match(/^canonical\/finance\/verifications\/(\d+)\/photo\/(front|back)$/);
  if (verificationPhoto && request.method === "GET") {
    const token = request.cookies.get(TOKEN_COOKIE)?.value;
    if (!token) return apiError("未登录", 401);
    let response: Response;
    try { response = await fetch(`${resolveApiOrigin()}/api/finance/verifications/${verificationPhoto[1]}/photo/${verificationPhoto[2]}`, { headers: { Authorization: `Bearer ${token}`, Accept: "image/*" }, cache: "no-store", signal: AbortSignal.timeout(20_000) }); }
    catch { return apiError("证件照片暂时无法读取", 503); }
    if (!response.ok) return apiError("证件照片无法读取", response.status);
    return new NextResponse(response.body, { status: response.status, headers: { "Content-Type": response.headers.get("content-type") || "image/jpeg", "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" } });
  }
  const withdrawalReceipt = path.match(/^canonical\/finance\/withdrawals\/([1-9]\d*)\/receipt$/);
  if (withdrawalReceipt && request.method === "GET") return proxyWithdrawalReceipt(request, withdrawalReceipt[1]);
  if (path === "canonical/verification/upload" && request.method === "POST") {
    const result = await upstreamMultipart(request, "/api/verification/upload", ["front", "back"], "身份证照片上传失败，请稍后重试");
    return result.ok ? apiSuccess(result.body.data, { source: "canonical-api" }) : upstreamFailure(result);
  }
  if (path === "canonical/user/avatar" && request.method === "POST") {
    const result = await upstreamMultipart(request, "/api/user/avatar", ["avatar"], "头像上传失败，请稍后重试");
    return result.ok ? apiSuccess(result.body.data, { source: "canonical-api" }) : upstreamFailure(result);
  }
  if (path === "canonical/community/media/upload" && request.method === "POST") {
    const result = await upstreamMultipart(
      request,
      "/api/community/media/upload",
      ["media"],
      "社区媒体上传失败，请稍后重试",
      [],
      240_000,
    );
    return result.ok ? apiSuccess(result.body.data, { source: "canonical-api" }) : upstreamFailure(result);
  }
  const markPaid = path.match(/^canonical\/finance\/withdrawals\/(\d+)\/mark-paid$/);
  if (markPaid && request.method === "POST") {
    const result = await upstreamMultipart(request, `/api/finance/withdrawals/${markPaid[1]}/mark-paid`, ["receipt"], "打款凭证上传失败，请稍后重试", ["bank_reference", "paid_amount_cny", "paid_at", "payee_confirmed", "reveal_token"]);
    return result.ok ? apiSuccess(result.body.data, { source: "canonical-api" }) : upstreamFailure(result);
  }
  const isRegistrationRequest = request.method === "POST" && (
    path === "auth/password/register"
    || path === "canonical/auth/register"
  );
  let body: JsonObject;
  try {
    body = await requestBody(request, isRegistrationRequest ? REGISTRATION_BODY_MAX_BYTES : undefined);
  } catch (error) {
    if (error instanceof RequestBodyTooLargeError) {
      return apiError(REGISTRATION_BODY_TOO_LARGE_MESSAGE, 413, "payload_too_large");
    }
    throw error;
  }

  if (path.startsWith("canonical/user/account-deletion")) {
    const matched = path.match(/^canonical\/user\/account-deletion\/(eligibility|verify|kai\/start|kai\/verify|submit|status)$/);
    if (!matched) return apiError("注销接口不存在", 404);
    const operation = matched[1] as AccountDeletionOperation;
    if (request.method !== accountDeletionMethods[operation]) return apiError("此注销接口不支持该请求方法", 405);
    if (request.nextUrl.search) return apiError("注销验证信息只能通过请求正文提交", 400);
    const proxyBody = operation === "kai/start"
      ? { ...body, return_url: `${publicOrigin(request)}/account-deletion` }
      : body;
    const result = await upstream(request, `/api/user/account-deletion/${operation}`, accountDeletionProxyOptions(operation, proxyBody));
    if (!result.ok) return upstreamFailure(result);
    const response = apiSuccess(result.body.data, { source: "canonical-api" });
    const currentBearer = request.cookies.get(TOKEN_COOKIE)?.value;
    if ((operation === "verify" || operation === "kai/verify") && currentBearer && typeof object(result.body.data).ticket === "string") {
      response.cookies.set(DELETION_SESSION_COOKIE, deletionSessionMarker(text(object(result.body.data).ticket), currentBearer), {
        httpOnly: true, sameSite: "strict", secure: requestIsHttps(request), path: "/", maxAge: 7 * 24 * 60 * 60,
      });
    }
    if ((operation === "submit" || operation === "status") && deletionRevokesNormalSession(result.body.data)) {
      const marker = request.cookies.get(DELETION_SESSION_COOKIE)?.value;
      const ticket = typeof body.ticket === "string" ? body.ticket : "";
      if (deletionMayClearSession(marker, ticket, currentBearer)) clearAuthCookie(request, response);
      if (object(result.body.data).status === "completed" && deletionMarkerMatchesTicket(marker, ticket)) {
        response.cookies.set(DELETION_SESSION_COOKIE, "", {
          httpOnly: true, sameSite: "strict", secure: requestIsHttps(request), path: "/", maxAge: 0,
        });
      }
    }
    return response;
  }

  if (path === "health" && request.method === "GET") {
    const result = await upstream(request, "/health", { auth: false });
    return result.ok ? apiSuccess({ mobile_backend: "ok" }) : upstreamFailure(result);
  }
  if (path === "auth/captcha" && request.method === "GET") {
    const result = await upstream(request, "/api/auth/captcha", { auth: false });
    return result.ok ? apiSuccess(result.body.data) : upstreamFailure(result);
  }
  if (path === "auth/recovery/config" && request.method === "GET") {
    return recoveryApiResponse(await upstream(request, "/api/auth/recovery/config", { auth: false }));
  }
  if (path === "user/recovery-email" && request.method === "GET") {
    return recoveryApiResponse(await upstream(request, "/api/user/recovery-email"));
  }
  if (path === "user/login-phone" && request.method === "GET") {
    return recoveryApiResponse(await upstream(request, "/api/user/login-phone"));
  }
  if (path === "user/login-phone" && request.method === "POST") {
    return recoveryApiResponse(await upstream(request, "/api/user/login-phone", {
      method: "POST",
      body: { phone: text(body.phone).trim(), password: text(body.password) },
    }));
  }
  if (path === "user/recovery-email/request-verification" && request.method === "POST") {
    return recoveryApiResponse(await upstream(request, "/api/user/recovery-email/request-verification", {
      method: "POST",
      body: {
        email: text(body.email).trim(),
        ...(typeof body.current_password === "string" && body.current_password.trim()
          ? { current_password: text(body.current_password) }
          : {}),
      },
    }));
  }
  if (path === "auth/email/verification/confirm" && request.method === "POST") {
    return recoveryApiResponse(await upstream(request, "/api/auth/email/verification/confirm", {
      method: "POST", auth: false, body: { token: text(body.token) },
    }));
  }
  if (path === "auth/email/password-reset/request" && request.method === "POST") {
    return recoveryApiResponse(await upstream(request, "/api/auth/email/password-reset/request", {
      method: "POST", auth: false, body: { email: text(body.email).trim() },
    }));
  }
  if (path === "auth/email/password-reset/confirm" && request.method === "POST") {
    return recoveryApiResponse(await upstream(request, "/api/auth/email/password-reset/confirm", {
      method: "POST", auth: false, body: { token: text(body.token), password: text(body.password) },
    }));
  }
  if (["auth/password/login", "auth/password/register"].includes(path) && request.method === "POST") {
    const register = path.endsWith("register");
    const payload = register ? {
      username: text(body.display_name).trim(),
      phone: text(body.identifier).trim(),
      password: text(body.password),
      captcha_key: text(body.captcha_key),
      captcha_code: text(body.captcha_code),
      invite_code: text(body.invite_code) || undefined,
      client_id: "web",
    } : { phone: text(body.identifier).trim(), password: text(body.password), client_id: "web" };
    const result = await upstream(request, register ? "/api/auth/register" : "/api/auth/login", {
      method: "POST", body: payload, auth: false,
    });
    if (!result.ok) return upstreamFailure(result);
    const data = object(result.body.data);
    const response = apiSuccess({ user: authUser(data.user) });
    setAuthCookie(request, response, text(data.token));
    return response;
  }
  if (path === "auth/me" && request.method === "GET") {
    const result = await upstream(request, "/api/user/profile");
    if (!result.ok) {
      const response = upstreamFailure(result);
      if (result.status === 401) clearAuthCookie(request, response);
      return response;
    }
    return apiSuccess({ user: authUser(result.body.data) });
  }
  if (path === "auth/logout" && request.method === "POST") {
    const result = await upstream(request, "/api/auth/logout", { method: "POST" });
    const response = result.ok || result.status === 401
      ? apiSuccess({
          logged_out: true,
          session_revoked: result.ok && Boolean(object(result.body.data).session_revoked),
        })
      : upstreamFailure(result);
    // Local sign-out must remain available when the API is temporarily down.
    // The upstream request has already captured the bearer needed to revoke
    // the server session whenever it is reachable.
    clearAuthCookie(request, response);
    return response;
  }
  if (path === "auth/kai/config" && request.method === "GET") {
    const result = await upstream(request, "/api/auth/kai/config", { auth: false });
    return result.ok ? apiSuccess(result.body.data) : upstreamFailure(result);
  }
  if (path === "auth/kai/start" && request.method === "GET") {
    const requestedIntent = request.nextUrl.searchParams.get("intent");
    const intent = requestedIntent === "register" || requestedIntent === "recover" ? requestedIntent : "login";
    const recovering = intent === "recover";
    const termsAccepted = !recovering && request.nextUrl.searchParams.get("terms_accepted") === "1";
    const result = await upstream(request, "/api/auth/kai/start", {
      method: "POST",
      auth: false,
      body: { intent, return_url: `${publicOrigin(request)}${recovering ? "/reset-password" : "/login"}`, client_id: "web", terms_accepted: termsAccepted },
    });
    if (!result.ok) return upstreamFailure(result);
    const authorizationUrl = text(object(result.body.data).authorization_url);
    if (!authorizationUrl) return apiError("统一认证未返回授权地址", 502);
    const response = NextResponse.redirect(authorizationUrl, 302);
    response.headers.set("Cache-Control", "private, no-store");
    response.headers.set("Referrer-Policy", "no-referrer");
    if (!recovering) {
      response.cookies.set(RETURN_TO_COOKIE, safeReturnPath(request.nextUrl.searchParams.get("return_to")), {
        httpOnly: true,
        sameSite: "lax",
        secure: requestIsHttps(request),
        path: "/",
        maxAge: 60 * 10,
      });
    }
    return response;
  }
  if (path === "auth/kai/exchange" && request.method === "POST") {
    const result = await upstream(request, "/api/auth/kai/exchange", {
      method: "POST", body: { ticket: text(body.ticket) }, auth: false,
    });
    if (!result.ok) return upstreamFailure(result);
    const data = object(result.body.data);
    const response = apiSuccess({
      user: authUser(data.user),
      return_to: safeReturnPath(request.cookies.get(RETURN_TO_COOKIE)?.value),
    });
    setAuthCookie(request, response, text(data.token));
    response.cookies.set(RETURN_TO_COOKIE, "", {
      httpOnly: true, sameSite: "lax", secure: requestIsHttps(request), path: "/", maxAge: 0,
    });
    return response;
  }
  if (path === "auth/kai/bind/start" && request.method === "POST") {
    const result = await upstream(request, "/api/auth/kai/bind/start", {
      method: "POST", body: { return_url: `${publicOrigin(request)}/account/settings` },
    });
    return result.ok ? apiSuccess(result.body.data) : upstreamFailure(result);
  }
  if (path === "auth/kai/bind/exchange" && request.method === "POST") {
    const result = await upstream(request, "/api/auth/kai/bind/exchange", {
      method: "POST", body: { ticket: text(body.ticket) },
    });
    return result.ok ? apiSuccess(result.body.data) : upstreamFailure(result);
  }
  if (path === "canonical/platform/capabilities" && request.method === "GET") {
    const result = await upstream(request, "/api/platform/capabilities", { auth: false });
    return result.ok
      ? apiSuccess(result.body.data, { source: "canonical-api" })
      : upstreamFailure(result);
  }
  if (path === "public/products" && request.method === "GET") {
    const query = new URLSearchParams(request.nextUrl.searchParams);
    const marketSource = query.get("market_source");
    const requestedPage = Math.max(1, Math.trunc(number(query.get("page") ?? undefined, 1)));
    const requestedPageSize = Math.min(100, Math.max(1, Math.trunc(number(query.get("page_size") ?? undefined, 24))));
    query.set("page", String(requestedPage));
    query.set("page_size", String(requestedPageSize));
    if (marketSource !== "kai" && marketSource !== "wod") query.delete("market_source");
    if (marketSource === "kai") query.set("representative", "true");
    else query.delete("representative");
    const cacheSeconds = marketSource === "kai" ? 300 : 15;
    const result = await upstream(request, "/api/products", { query, auth: false, revalidate: cacheSeconds });
    if (!result.ok) return upstreamFailure(result);
    const page = pageEnvelope(result.body.data);
    const products = page.data.map((item) => product(item));
    return publicApiSuccess(products, { ...page.meta, count: products.length, real_data_only: true, server_rental_available: true, payment_mode: "mobile_wallet", source: "canonical-api" }, marketSource === "kai" ? 300 : 5);
  }
  const productMatch = path.match(/^public\/products\/(\d+)$/);
  if (productMatch && request.method === "GET") {
    const result = await upstream(request, `/api/products/${productMatch[1]}`, { auth: false, revalidate: 10 });
    return result.ok ? publicApiSuccess(product(result.body.data), { real_data_only: true, server_rental_available: true, payment_mode: "mobile_wallet", source: "canonical-api" }, 5) : upstreamFailure(result);
  }
  if (path === "public/market/ranking" && request.method === "GET") return marketRanking(request);
  if (path === "public/market/summary" && request.method === "GET") return marketSummary(request);
  if (path === "account/summary" && request.method === "GET") return accountSummary(request);

  if (path === "account/orders/direct" && request.method === "POST") {
    const result = await upstream(request, "/api/orders", {
      method: "POST",
      body: {
        product_id: number(body.product_id),
        quantity: number(body.quantity, 1),
        hours: number(body.hours),
        purchase_type: text(body.purchase_type, "usage"),
        expected_unit_price_card_hours: number(body.expected_unit_price_card_hours),
        client_request_id: text(body.client_request_id, text(request.headers.get("idempotency-key"))).slice(0, 64) || undefined,
      },
    });
    return result.ok ? apiSuccess({ order: order(result.body.data) }) : upstreamFailure(result);
  }
  const accountOrder = path.match(/^account\/orders(?:\/(\d+))?(?:\/(confirm|complete|cancel|dispute|renew))?$/);
  if (accountOrder) {
    const id = accountOrder[1];
    const action = accountOrder[2];
    if (!id && request.method === "GET") {
      const query = new URLSearchParams(request.nextUrl.searchParams);
      const status = query.get("status");
      query.delete("status");
      if (status) query.set("status_filter", status);
      const result = await upstream(request, "/api/orders", { query });
      if (!result.ok) return upstreamFailure(result);
      const items = Array.isArray(result.body.data) ? result.body.data : [];
      return apiSuccess(items.map((item) => order(item)), { page: 1, page_size: items.length || 1, total: items.length, total_pages: 1 });
    }
    if (id && !action && request.method === "GET") {
      const result = await upstream(request, `/api/orders/${id}`);
      return result.ok ? apiSuccess(order(result.body.data)) : upstreamFailure(result);
    }
    if (id && action && request.method === "POST") {
      const upstreamAction = action === "complete" ? "confirm" : action;
      const result = await upstream(request, `/api/orders/${id}/${upstreamAction}`, {
        method: "POST",
        body: action === "renew"
          ? {
              hours: number(body.hours),
              client_request_id: text(body.client_request_id, text(request.headers.get("idempotency-key"))).slice(0, 64),
            }
          : action === "dispute"
            ? { reason: text(body.reason) }
            : undefined,
      });
      if (!result.ok) return upstreamFailure(result);
      const detail = await upstream(request, `/api/orders/${id}`);
      return detail.ok ? apiSuccess(order(detail.body.data)) : apiSuccess(result.body.data);
    }
  }

  const supplierOrder = path.match(/^supplier\/orders(?:\/(\d+))?(?:\/(mark-delivered))?$/);
  if (supplierOrder) {
    const id = supplierOrder[1];
    const action = supplierOrder[2];
    const list = async () => {
      const query = new URLSearchParams(request.nextUrl.searchParams);
      const status = query.get("status");
      query.delete("status");
      if (status) query.set("status_filter", status);
      return upstream(request, "/api/supplier/orders", { query });
    };
    if (!id && request.method === "GET") {
      const result = await list();
      if (!result.ok) return upstreamFailure(result);
      const items = Array.isArray(result.body.data) ? result.body.data : [];
      return apiSuccess(items.map((item) => order(item, true)), { page: 1, page_size: items.length || 1, total: items.length, total_pages: 1 });
    }
    if (id && !action && request.method === "GET") {
      const result = await list();
      if (!result.ok) return upstreamFailure(result);
      const found = (Array.isArray(result.body.data) ? result.body.data : []).find((item) => number(object(item).id) === number(id));
      return found ? apiSuccess(order(found, true)) : apiError("订单不存在", 404);
    }
    if (id && action === "mark-delivered" && request.method === "POST") {
      const result = await upstream(request, `/api/orders/${id}/deliver`, { method: "POST", body: { ssh_info: body.note } });
      if (!result.ok) return upstreamFailure(result);
      const refreshed = await list();
      const found = refreshed.ok && Array.isArray(refreshed.body.data)
        ? refreshed.body.data.find((item) => number(object(item).id) === number(id))
        : null;
      return found ? apiSuccess(order(found, true)) : apiSuccess(result.body.data);
    }
  }

  if (path === "supplier/application" && request.method === "GET") {
    const result = await upstream(request, "/api/supplier/mine");
    if (result.ok) {
      const supplier = object(result.body.data);
      return apiSuccess(supplier.status === "not_registered" ? { status: "not_applied" } : supplier);
    }
    if (result.status === 404 || result.status === 403) return apiSuccess({ status: "not_applied" });
    return upstreamFailure(result);
  }
  if (path === "supplier/application" && request.method === "POST") {
    const result = await upstream(request, "/api/supplier/register", { method: "POST", body: {
      company_name: body.company_name,
      contact: body.contact_name,
      phone: body.contact_phone,
      region: body.region || undefined,
      desc: body.description || undefined,
    } });
    return result.ok ? apiSuccess(result.body.data, {}, 201) : upstreamFailure(result);
  }

  if (path === "admin/supplier-applications" && request.method === "GET") {
    const result = await upstream(request, "/api/supplier/admin/applications", { query: request.nextUrl.searchParams });
    if (!result.ok) return upstreamFailure(result);
    const page = pageEnvelope(result.body.data);
    return apiSuccess(page.data, page.meta);
  }
  const supplierReviewMatch = path.match(/^admin\/supplier-applications\/(\d+)\/(approve|reject)$/);
  if (supplierReviewMatch && request.method === "POST") {
    const result = await upstream(request, `/api/supplier/admin/applications/${supplierReviewMatch[1]}/${supplierReviewMatch[2]}`, {
      method: "POST",
      body: { version: number(body.version, 1), note: text(body.note) || undefined },
    });
    return result.ok ? apiSuccess(result.body.data) : upstreamFailure(result);
  }

  if (/^account\/addresses(?:\/\d+)?(?:\/default)?$/.test(path)) {
    const suffix = path.slice("account/addresses".length);
    const payload = isMutation(request.method) ? {
      name: body.recipient_name,
      phone: body.phone,
      province: body.province,
      city: body.city,
      district: body.district || "",
      detail: body.address_line,
      label: body.label || undefined,
      is_default: body.is_default,
    } : undefined;
    const result = await upstream(request, `/api/addresses${suffix}`, {
      method: request.method === "PATCH" ? "PUT" : request.method,
      body: request.method === "POST" && suffix.endsWith("/default") ? undefined : payload,
    });
    if (!result.ok) return upstreamFailure(result);
    if (Array.isArray(result.body.data)) return apiSuccess(result.body.data.map(address));
    if (request.method === "DELETE" || suffix.endsWith("/default")) return apiSuccess(result.body.data);
    return apiSuccess(address(result.body.data));
  }

  if (/^notifications(?:\/.*)?$/.test(path)) {
    const suffix = path.slice("notifications".length);
    const result = await upstream(request, `/api/notifications${suffix}`, {
      method: request.method === "PATCH" ? "POST" : request.method,
      body: isMutation(request.method) ? body : undefined,
      query: request.nextUrl.searchParams,
    });
    if (!result.ok) return upstreamFailure(result);
    if (path === "notifications/unread-count") return apiSuccess({ unread_count: number(object(result.body.data).unread) });
    if (path === "notifications/read-all") return apiSuccess({ updated_count: number(object(result.body.data).changed) });
    if (path === "notifications") {
      const page = pageEnvelope(result.body.data);
      return apiSuccess((page.data as unknown[]).map(notice), { ...page.meta, unread: number(object(result.body.data).unread) });
    }
    return apiSuccess(result.body.data);
  }

  const directMappings: Array<[RegExp, string]> = [
    [/^account\/buy-requests(\/.*)?$/, "/api/buy-requests$1"],
    [/^buy-requests$/, "/api/buy-requests"],
    [/^account\/assets(\/.*)?$/, "/api/assets$1"],
  ];
  for (const [pattern, replacement] of directMappings) {
    if (!pattern.test(path)) continue;
    const upstreamPath = path.replace(pattern, replacement);
    const result = await upstream(request, upstreamPath, { body: isMutation(request.method) ? body : undefined, query: request.nextUrl.searchParams });
    if (!result.ok) return upstreamFailure(result);
    const paged = object(result.body.data);
    if (Array.isArray(paged.items)) {
      const page = pageEnvelope(paged);
      return apiSuccess(page.data, page.meta);
    }
    return apiSuccess(result.body.data);
  }

  if (path === "account/wallet" && request.method === "GET") {
    const [result, ledgerResult] = await Promise.all([
      upstream(request, "/api/wallet"),
      upstream(request, "/api/wallet/ledger", { query: new URLSearchParams({ page_size: "20" }) }),
    ]);
    if (!result.ok) return upstreamFailure(result);
    const wallet = object(result.body.data);
    const ledger = ledgerResult.ok ? array(object(ledgerResult.body.data).items) : [];
    return apiSuccess({
      provider: {
        kind: "payment", provider: "canonical-api", status: wallet.payment_service_enabled ? "configured" : "disabled",
        configured: Boolean(wallet.payment_service_enabled), capabilities: ["wallet", "ledger"], reason: wallet.payment_service_enabled ? null : "手机端支付尚未启用",
      },
      balances: [{ currency: "CARD_HOURS", available: number(wallet.balance).toFixed(2), frozen: number(wallet.frozen).toFixed(2) }],
      payment_intents: ledger.map((entry) => ({
        id: number(entry.id),
        payment_no: `LEDGER-${number(entry.id)}`,
        order_id: entry.ref_order_id == null ? null : number(entry.ref_order_id),
        purpose: text(entry.remark, text(entry.type)),
        amount: number(entry.amount).toFixed(4),
        currency: "CARD_HOURS",
        status: text(entry.direction) === "in" ? "succeeded" : text(entry.type),
        provider: "canonical-api",
        checkout_url: null,
        expires_at: null,
        created_at: text(entry.created_at),
        updated_at: text(entry.created_at),
        version: 1,
      })), ledger_mode: "mobile_ledger",
    });
  }
  if (path === "account/security/password" && request.method === "POST") {
    const result = await upstream(request, "/api/user/password", { method: "POST", body: { old_password: body.current_password, new_password: body.new_password } });
    return result.ok ? apiSuccess({
      changed: true,
      revoked_other_sessions: number(object(result.body.data).revoked_other_sessions),
    }) : upstreamFailure(result);
  }

  if (path.startsWith("canonical/")) {
    const canonicalPath = path.slice("canonical/".length);
    if (!canonicalPath || canonicalPath.includes("..")) return apiError("无效的业务 API 路径", 400);
    if (/^auth\/(?:login|logout|register|kai\/(?:exchange|callback))$/.test(canonicalPath)) {
      return apiError("Web 鉴权必须使用 HttpOnly Cookie 适配接口", 403, "web_auth_adapter_required");
    }
    if (request.method === "GET" && canonicalPath === "market/prices/latest") return publicMarketLatest(request);
    const publicMarketRead = request.method === "GET" && /^(?:market\/(?:models|ranking|sources\/status|prices\/(?:candles|history))|products\/quote\/regional)$/.test(canonicalPath);
    const result = await upstream(request, `/api/${canonicalPath}`, {
      body: isMutation(request.method) ? body : undefined,
      query: request.nextUrl.searchParams,
      ...(publicMarketRead ? {
        auth: false,
        revalidate: canonicalPath.includes("history") || canonicalPath.includes("candles") ? 120 : 30,
      } : {}),
    });
    return result.ok
      ? publicMarketRead
        ? publicApiSuccess(result.body.data, { source: "canonical-api" }, 10)
        : apiSuccess(result.body.data, { source: "canonical-api" })
      : upstreamFailure(result);
  }

  return unavailable(path);
}
