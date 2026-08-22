import "server-only";

import { NextRequest, NextResponse } from "next/server";
import { resolveApiOrigin } from "@/lib/server/api-origin";
import {
  callCanonicalApi as upstream,
  callCanonicalMultipart as upstreamMultipart,
  canonicalErrorMessage,
  type CanonicalApiResult,
  WEB_TOKEN_COOKIE as TOKEN_COOKIE,
} from "@/lib/server/canonical-api-client";

const RETURN_TO_COOKIE = "wod_web_return_to";

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
}

function array(value: unknown): JsonObject[] {
  return Array.isArray(value) ? value.map(object) : [];
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

async function requestBody(request: NextRequest): Promise<JsonObject> {
  if (!isMutation(request.method)) return {};
  const contentType = request.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) return {};
  try {
    return object(await request.json());
  } catch {
    return {};
  }
}

function upstreamFailure(result: CanonicalApiResult) {
  return apiError(canonicalErrorMessage(result), result.status || 502);
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

function safeReturnPath(value: unknown) {
  const path = text(value, "/");
  return path.startsWith("/") && !path.startsWith("//") ? path : "/";
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
  if (!/^[1-9]\d*$/.test(userId) || !/^[0-9a-f]{32}\.(?:jpg|png|webp|mp4|webm)$/.test(filename)) return apiError("社区媒体不存在", 404);
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

async function proxyCheckout(request: NextRequest, token: string) {
  let response: Response;
  try {
    response = await fetch(`${resolveApiOrigin()}/api/payments/mapay/checkout/${encodeURIComponent(token)}`, {
      headers: { Accept: "text/html" },
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    return new NextResponse("支付页面暂时无法打开", { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } });
  }
  return new NextResponse(response.body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") || "text/html; charset=utf-8",
      "Cache-Control": "private, no-store",
      "Referrer-Policy": "no-referrer",
      "X-Content-Type-Options": "nosniff",
      "X-Frame-Options": "DENY",
    },
  });
}

function product(value: unknown) {
  const item = object(value);
  const memory = text(item.memory);
  const memoryGb = number(memory.match(/\d+(?:\.\d+)?/)?.[0]);
  const price = number(item.price);
  const stock = number(item.stock);
  return {
    id: number(item.id),
    supplier_id: number(item.supplier_id),
    name: text(item.name),
    gpu_model: text(item.gpu_model),
    memory,
    gpu_memory_gb: memoryGb,
    region: text(item.region_name, text(item.region_code, text(item.city, "未标注"))),
    description: text(item.desc),
    cpu_cores: null,
    ram_gb: null,
    disk_gb: null,
    bandwidth_mbps: null,
    unit_price_ch: price,
    price: { amount: price.toFixed(4), currency: "CNY", unit: "GPU·小时" },
    total_quantity: number(item.reported_stock, stock),
    available_quantity: stock,
    source_name: text(item.supplier_name, text(item.market_source, "北斗 kai")),
    source_observed_at: text(item.price_updated_at) || null,
    server_online: Boolean(item.purchasable),
    purchasable: Boolean(item.purchasable),
    purchase_unavailable_reason: text(item.purchase_unavailable_reason) || null,
    cycle: Array.isArray(item.cycle) ? item.cycle.map((entry) => number(entry)).filter(Boolean) : [30],
    image_url: text(item.image_url) || null,
    market_source: text(item.market_source, "wod"),
  };
}

function pageEnvelope(value: unknown) {
  const page = object(value);
  const items = Array.isArray(page.items) ? page.items : [];
  const current = number(page.page, 1);
  const size = number(page.page_size, Math.max(items.length, 1));
  const total = number(page.total, items.length);
  return {
    data: items,
    meta: { page: current, page_size: size, total, total_pages: Math.max(1, Math.ceil(total / size)) },
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
    action_path: text(item.action_url) || null,
    is_read: Boolean(item.is_read),
    read_at: null,
    created_at: text(item.created_at),
  };
}

function mapOrderStatus(status: string) {
  return ({ paid: "confirmed", delivering: "delivered", running: "completed", canceled: "cancelled" } as Record<string, string>)[status] || status;
}

function order(value: unknown, supplierView = false) {
  const item = object(value);
  const mappedStatus = mapOrderStatus(text(item.status));
  const supplierName = text(item.supplier_name, "北斗 kai 商家");
  const available: string[] = [];
  if (!supplierView && item.status === "delivering") available.push("complete");
  if (!supplierView && item.status === "paid") available.push("cancel");
  if (!supplierView && ["completed", "running"].includes(text(item.status)) && text(item.purchase_type, "usage") === "usage") available.push("renew");
  if (supplierView && item.status === "paid") available.push("mark_delivered");
  return {
    id: number(item.id),
    order_no: text(item.order_no),
    status: mappedStatus,
    buyer_id: number(item.user_id),
    supplier_id: number(item.supplier_id),
    buy_request_id: null,
    accepted_quote_id: null,
    product_id: number(item.product_id),
    order_source: "direct",
    environment: "live",
    payment_status: ["paid", "delivering", "completed", "running"].includes(text(item.status)) ? "paid" : "pending",
    duration_hours: number(item.cycle_days) * 24,
    amount: number(item.amount).toFixed(4),
    currency: "CNY",
    price_unit: "订单总额",
    quantity: number(item.quantity, 1),
    purchase_type: text(item.purchase_type, "usage"),
    cycle_days: number(item.cycle_days),
    end_at: text(item.end_at) || null,
    remaining_days: number(item.remaining_days),
    snapshot: {
      payment_mode: "mobile_wallet",
      product: {
        resource_no: `WOD-P-${number(item.product_id)}`,
        name: text(item.product_name, "算力资源"),
        gpu_model: text(item.gpu_model),
        region: "",
        unit_price: "",
      },
    },
    buyer_confirmed_at: item.status === "completed" || item.status === "running" ? item.start_at : null,
    supplier_confirmed_at: item.status === "delivering" || item.status === "completed" || item.status === "running" ? item.created_at : null,
    confirmed_at: item.start_at || null,
    delivery_started_at: item.status === "delivering" ? item.created_at : null,
    delivered_at: item.status === "delivering" ? item.created_at : null,
    completed_at: item.status === "completed" || item.status === "running" ? item.start_at : null,
    cancelled_at: item.status === "canceled" ? item.created_at : null,
    cancel_reason: null,
    delivery_note: text(item.ssh_info) || null,
    created_at: text(item.created_at),
    updated_at: text(item.created_at),
    version: 1,
    buyer: { display_name: text(item.buyer_name, "买家") },
    supplier: { display_name: supplierName, company_name: supplierName },
    available_actions: available,
    events: [],
  };
}

function modelMemory(model: string, variant: string) {
  const matched = `${variant} ${model}`.match(/(?:^|\D)(\d{2,3})\s*(?:GB|G)(?:\D|$)/i);
  return matched ? number(matched[1]) : undefined;
}

async function marketRanking(request: NextRequest) {
  const ranking = await upstream(request, "/api/market/ranking", { auth: false });
  if (!ranking.ok) return upstreamFailure(ranking);
  const rankingData = object(ranking.body.data);
  const entries = array(rankingData.items).slice(0, 12).map((entry) => ({
    gpu_model: text(entry.gpu_model),
    gpu_variant: text(entry.gpu_variant),
    median_price_cny: number(entry.median_price_cny),
    change_24h: number(entry.change_24h),
    available_gpu_count: number(entry.available_gpu_count),
    source_count: number(entry.source_count),
    sources: Array.isArray(entry.sources) ? entry.sources.map((source) => text(source)).filter(Boolean) : [],
    history_day_count: number(entry.history_day_count),
    history_point_count: number(entry.history_point_count),
    market_status: text(entry.market_status),
  }));
  return apiSuccess(entries, {
    observed_at: text(rankingData.server_time),
    count: entries.length,
    source: "canonical-api",
  });
}

async function marketSummary(request: NextRequest) {
  const ranking = await upstream(request, "/api/market/ranking", { auth: false });
  if (!ranking.ok) return upstreamFailure(ranking);
  const rankingData = object(ranking.body.data);
  const entries = array(rankingData.items).slice(0, 12);
  const withHistory = await Promise.all(entries.map(async (entry) => {
    const model = text(entry.gpu_model);
    const variant = text(entry.gpu_variant);
    const query = new URLSearchParams({ model, range: "30d", sources: "wod,vast,autodl" });
    if (variant) query.set("variant", variant);
    const historyResult = await upstream(request, "/api/market/prices/history", { query, auth: false });
    const historyData = historyResult.ok ? object(historyResult.body.data) : {};
    const byDay = new Map<string, number[]>();
    for (const series of array(historyData.series)) {
      for (const point of array(series.points)) {
        const date = text(point.time).slice(0, 10);
        const price = number(point.price_cny, NaN);
        if (date && Number.isFinite(price) && price > 0) byDay.set(date, [...(byDay.get(date) || []), price]);
      }
    }
    const history = [...byDay.entries()].sort(([a], [b]) => b.localeCompare(a)).map(([date, prices]) => ({
      date,
      median: prices.sort((a, b) => a - b)[Math.floor(prices.length / 2)],
    }));
    const current = number(entry.median_price_cny);
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
  }));
  return apiSuccess(withHistory, {
    observed_at: text(rankingData.server_time),
    history_updated_at: text(rankingData.server_time),
    count: withHistory.length,
    source: "canonical-api",
  });
}

async function accountSummary(request: NextRequest) {
  const [profileResult, ordersResult, assetsResult] = await Promise.all([
    upstream(request, "/api/user/profile"),
    upstream(request, "/api/orders"),
    upstream(request, "/api/assets"),
  ]);
  if (!profileResult.ok) return upstreamFailure(profileResult);
  const profile = authUser(profileResult.body.data);
  const orders = ordersResult.ok && Array.isArray(ordersResult.body.data) ? ordersResult.body.data : [];
  const assets = assetsResult.ok ? array(object(assetsResult.body.data).items) : [];
  return apiSuccess({
    user: profile,
    metrics: {
      active_orders: orders.filter((item) => !["completed", "running", "canceled"].includes(text(object(item).status))).length,
      active_assets: assets.length,
      hosted_devices: 0,
      open_requests: 0,
    },
    supplier_status: profile.supplier_status,
    services: { payment: false, kyc: false },
  });
}

function unavailable(path: string) {
  return apiError(`此 Web 模块没有手机端数据源，已停用：${path}`, 503, "mobile_source_unavailable");
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
  const checkout = path.match(/^canonical\/payments\/mapay\/checkout\/([A-Za-z0-9_-]+)$/);
  if (checkout && request.method === "GET") return proxyCheckout(request, checkout[1]);
  const avatar = path.match(/^canonical\/user\/avatars\/(avatar_\d+\.(?:jpg|png|webp))$/);
  if (avatar && request.method === "GET") return proxyAvatar(request, avatar[1]);
  const communityMedia = path.match(/^canonical\/uploads\/community\/([1-9]\d*)\/([0-9a-f]{32}\.(?:jpg|png|webp|mp4|webm))$/);
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
  if (path === "canonical/verification/upload" && request.method === "POST") {
    const result = await upstreamMultipart(request, "/api/verification/upload", ["front", "back"], "身份证照片上传失败，请稍后重试");
    return result.ok ? apiSuccess(result.body.data, { source: "canonical-api" }) : upstreamFailure(result);
  }
  if (path === "canonical/user/avatar" && request.method === "POST") {
    const result = await upstreamMultipart(request, "/api/user/avatar", ["avatar"], "头像上传失败，请稍后重试");
    return result.ok ? apiSuccess(result.body.data, { source: "canonical-api" }) : upstreamFailure(result);
  }
  if (path === "canonical/community/media/upload" && request.method === "POST") {
    const result = await upstreamMultipart(request, "/api/community/media/upload", ["media"], "社区媒体上传失败，请稍后重试");
    return result.ok ? apiSuccess(result.body.data, { source: "canonical-api" }) : upstreamFailure(result);
  }
  const markPaid = path.match(/^canonical\/finance\/withdrawals\/(\d+)\/mark-paid$/);
  if (markPaid && request.method === "POST") {
    const result = await upstreamMultipart(request, `/api/finance/withdrawals/${markPaid[1]}/mark-paid`, ["receipt"], "打款凭证上传失败，请稍后重试", ["bank_reference", "paid_amount_cny", "paid_at", "payee_confirmed", "reveal_token"]);
    return result.ok ? apiSuccess(result.body.data, { source: "canonical-api" }) : upstreamFailure(result);
  }
  const body = await requestBody(request);

  if (path === "health" && request.method === "GET") {
    const result = await upstream(request, "/health", { auth: false });
    return result.ok ? apiSuccess({ mobile_backend: "ok" }) : upstreamFailure(result);
  }
  if (path === "auth/captcha" && request.method === "GET") {
    const result = await upstream(request, "/api/auth/captcha", { auth: false });
    return result.ok ? apiSuccess(result.body.data) : upstreamFailure(result);
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
    } : { phone: text(body.identifier).trim(), password: text(body.password) };
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
    const response = apiSuccess({ logged_out: true });
    clearAuthCookie(request, response);
    return response;
  }
  if (path === "auth/kai/config" && request.method === "GET") {
    const result = await upstream(request, "/api/auth/kai/config", { auth: false });
    return result.ok ? apiSuccess(result.body.data) : upstreamFailure(result);
  }
  if (path === "auth/kai/start" && request.method === "GET") {
    const intent = request.nextUrl.searchParams.get("intent") === "register" ? "register" : "login";
    const result = await upstream(request, "/api/auth/kai/start", {
      method: "POST",
      auth: false,
      body: { intent, return_url: `${publicOrigin(request)}/login` },
    });
    if (!result.ok) return upstreamFailure(result);
    const authorizationUrl = text(object(result.body.data).authorization_url);
    if (!authorizationUrl) return apiError("统一认证未返回授权地址", 502);
    const response = NextResponse.redirect(authorizationUrl, 302);
    response.cookies.set(RETURN_TO_COOKIE, safeReturnPath(request.nextUrl.searchParams.get("return_to")), {
      httpOnly: true,
      sameSite: "lax",
      secure: requestIsHttps(request),
      path: "/",
      maxAge: 60 * 10,
    });
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
  if (path === "public/products" && request.method === "GET") {
    const result = await upstream(request, "/api/products", { query: request.nextUrl.searchParams, auth: false });
    if (!result.ok) return upstreamFailure(result);
    const page = pageEnvelope(result.body.data);
    return apiSuccess((page.data as unknown[]).map(product), { ...page.meta, count: page.meta.total, real_data_only: true, server_rental_available: true, payment_mode: "mobile_wallet", source: "canonical-api" });
  }
  const productMatch = path.match(/^public\/products\/(\d+)$/);
  if (productMatch && request.method === "GET") {
    const result = await upstream(request, `/api/products/${productMatch[1]}`, { auth: false });
    return result.ok ? apiSuccess(product(result.body.data), { real_data_only: true, server_rental_available: true, payment_mode: "mobile_wallet", source: "canonical-api" }) : upstreamFailure(result);
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
        cycle_days: number(body.cycle_days, 30),
        purchase_type: text(body.purchase_type, "usage"),
        client_request_id: text(body.client_request_id, text(request.headers.get("idempotency-key"))).slice(0, 64) || undefined,
      },
    });
    return result.ok ? apiSuccess({ order: order(result.body.data) }) : upstreamFailure(result);
  }
  const accountOrder = path.match(/^account\/orders(?:\/(\d+))?(?:\/(confirm|complete|cancel|renew))?$/);
  if (accountOrder) {
    const id = accountOrder[1];
    const action = accountOrder[2];
    if (!id && request.method === "GET") {
      const query = new URLSearchParams(request.nextUrl.searchParams);
      const status = query.get("status");
      query.delete("status");
      if (status) query.set("status_filter", ({ confirmed: "paid", delivered: "delivering", cancelled: "canceled" } as Record<string, string>)[status] || status);
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
      const result = await upstream(request, `/api/orders/${id}/${upstreamAction}`, { method: "POST", body: action === "renew" ? { product_id: 0, cycle_days: number(body.cycle_days, 30) } : undefined });
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
      if (status) query.set("status_filter", ({ confirmed: "paid", delivered: "delivering", cancelled: "canceled" } as Record<string, string>)[status] || status);
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
    return result.ok ? apiSuccess({ changed: true, revoked_other_sessions: 0 }) : upstreamFailure(result);
  }

  if (path.startsWith("canonical/")) {
    const canonicalPath = path.slice("canonical/".length);
    if (!canonicalPath || canonicalPath.includes("..")) return apiError("无效的业务 API 路径", 400);
    if (/^auth\/(?:login|register|kai\/(?:exchange|callback))$/.test(canonicalPath)) {
      return apiError("Web 鉴权必须使用 HttpOnly Cookie 适配接口", 403, "web_auth_adapter_required");
    }
    const result = await upstream(request, `/api/${canonicalPath}`, {
      body: isMutation(request.method) ? body : undefined,
      query: request.nextUrl.searchParams,
    });
    return result.ok ? apiSuccess(result.body.data, { source: "canonical-api" }) : upstreamFailure(result);
  }

  return unavailable(path);
}
