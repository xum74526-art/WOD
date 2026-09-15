"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle, Cpu, HardDrives, ShieldCheck, TerminalWindow, Wallet, X } from "@phosphor-icons/react";
import { ApiError, getCurrentUser, type AuthUser } from "@/lib/api";
import { createDirectOrder, getPublicProduct, type PublicProduct } from "@/lib/commerce-api";
import { loginHref } from "@/lib/auth-navigation";
import { ProductImage } from "@/components/product-image";
import { getUserRebate, type RebateSummary } from "@/lib/mobile-business-api";
import { clampPurchaseHours, estimateProductExpiryRebate, type ProductPurchaseType } from "@/lib/product-purchase";
import { useI18n } from "@/components/locale-root";
import { localizeSupplierName } from "@/lib/market-localization";
import { usePlatformCapabilities } from "@/lib/use-platform-capabilities";
import { directOrderIntentSignature, ensureDirectOrderIntent, type DirectOrderIntent } from "@/lib/web-business-contract";
import { normalizeInquiryRegionRequirement } from "@/lib/request-navigation";

const DEFAULT_PURCHASE_HOURS = [1, 6, 12, 24, 72, 168];

export function ProductDetail({ productId }: { productId: string }) {
  const router = useRouter();
  const { locale, t } = useI18n();
  const { capabilities } = usePlatformCapabilities();
  const directTradeEnabled = capabilities.direct_trade_enabled === true;
  const matchmakingEnabled = capabilities.matchmaking_enabled === true;
  const [product, setProduct] = useState<PublicProduct | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [rebate, setRebate] = useState<RebateSummary | null>(null);
  const [error, setError] = useState("");
  const [authLoading, setAuthLoading] = useState(true);
  const [purchaseHours, setPurchaseHours] = useState(24);
  const [quantity, setQuantity] = useState(1);
  const purchaseType = "usage" as const satisfies ProductPurchaseType;
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const orderSubmissionInFlight = useRef(false);
  const pendingOrderIntent = useRef<DirectOrderIntent | null>(null);

  useEffect(() => {
    getPublicProduct(Number(productId))
      .then((payload) => {
        setProduct(payload.data);
        const options = payload.data.purchase_hour_options.filter((hours) => Number.isInteger(hours) && hours > 0);
        const presets = options.length ? options : DEFAULT_PURCHASE_HOURS;
        setPurchaseHours(presets.includes(24) ? 24 : presets[0]);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "算力资源读取失败"));
    getCurrentUser()
      .then(({ user: current }) => setUser(current))
      .catch(() => setUser(null))
      .finally(() => setAuthLoading(false));
  }, [productId]);

  useEffect(() => {
    if (!directTradeEnabled || !user) { setRebate(null); return; }
    let cancelled = false;
    void getUserRebate()
      .then((value) => { if (!cancelled) setRebate(value); })
      .catch(() => { if (!cancelled) setRebate(null); });
    return () => { cancelled = true; };
  }, [directTradeEnabled, user]);

  useEffect(() => {
    if (!directTradeEnabled) {
      pendingOrderIntent.current = null;
      setConfirmOpen(false);
    }
  }, [directTradeEnabled]);

  const walletTotal = useMemo(
    () => product ? product.unit_price_ch * purchaseHours * quantity : 0,
    [purchaseHours, product, quantity],
  );
  const rebateEstimate = useMemo(
    () => estimateProductExpiryRebate(walletTotal, purchaseType, rebate),
    [purchaseType, rebate, walletTotal],
  );
  const currentRebateRate = Number(rebate?.current_rate || 0);
  const minimumRebateOrder = Number(rebate?.minimum_order_amount || 0);
  const rebateCapRemaining = Number(rebate?.cap_remaining);
  const rebateCapKnown = Number.isFinite(rebateCapRemaining) && rebateCapRemaining >= 0;
  const rebateAmountText = rebate?.rewards_enabled && rebateEstimate.ratePercent > 0
    ? t("product.rebate.amount", "+{amount} 卡时", { amount: rebateEstimate.amount.toFixed(2) })
    : "—";
  const rebatePolicyText = !user
    ? t("product.rebate.login", "登录后读取个人等级返佣政策。")
    : !rebate
      ? t("product.rebate.unavailable", "暂时无法读取个人返佣政策，请稍后刷新。")
      : !rebate.rewards_enabled
        ? t("product.rebate.disabled", "个人购买返佣当前未开启。")
        : !rebateCapKnown
          ? t("product.rebate.unavailable", "暂时无法读取个人返佣政策，请稍后刷新。")
          : walletTotal < minimumRebateOrder
            ? t("product.rebate.minimum", "当前个人等级 {current}%；订单满 {amount} 卡时后参与个人购买返佣。", { current: currentRebateRate, amount: minimumRebateOrder.toFixed(2) })
            : rebateCapRemaining <= 0
              ? t("product.rebate.capExhausted", "当前个人等级 {current}%，本月返佣额度已用完。", { current: currentRebateRate })
              : t("product.rebate.tierStable", "当前及本单预计个人等级均为 {rate}%。", { rate: rebateEstimate.ratePercent });

  function normalizeHours(value = purchaseHours) {
    setPurchaseHours(clampPurchaseHours(value));
  }

  function ensurePendingOrder(hours = clampPurchaseHours(purchaseHours)) {
    if (!product) return null;
    const input = {
      product_id: product.id,
      quantity,
      hours,
      purchase_type: purchaseType,
      expected_unit_price_card_hours: product.unit_price_ch,
    };
    const intent = ensureDirectOrderIntent(
      pendingOrderIntent.current,
      directOrderIntentSignature(input),
      () => crypto.randomUUID(),
    );
    pendingOrderIntent.current = intent;
    return { input, requestId: intent.requestId };
  }

  function cancelPurchase() {
    if (busy) return;
    pendingOrderIntent.current = null;
    setConfirmOpen(false);
  }

  function beginInquiry() {
    if (!product || !matchmakingEnabled || product.inquiry_available === false) return;
    normalizeHours();
    const region = normalizeInquiryRegionRequirement(product.region);
    const params = new URLSearchParams({
      create: "1",
      product_id: String(product.id),
      gpu_model: product.gpu_model,
      gpu_variant: product.memory || "",
      quantity: String(quantity),
      gpu_hours: String(clampPurchaseHours(purchaseHours)),
      product_name: product.name,
      seller_name: product.seller_name || product.supplier_name || product.source_name || "",
      source: product.seller_type === "kai_self_operated" || product.market_source === "kai" ? "kai" : "merchant",
    });
    if (region) params.set("region", region);
    if (product.supplier_id != null) params.set("supplier_id", String(product.supplier_id));
    const requestHref = `/account/requests?${params.toString()}`;
    router.push(user ? requestHref : loginHref(requestHref));
  }

  function beginPurchase() {
    if (!directTradeEnabled) return;
    if (!user) { router.push(loginHref(`/market/products/${productId}`)); return; }
    if (!product?.purchasable || product.purchase_unit !== "hour") return;
    const hours = clampPurchaseHours(purchaseHours);
    normalizeHours(hours);
    ensurePendingOrder(hours);
    setConfirmOpen(true);
  }

  async function purchase() {
    if (!user) { router.push(loginHref(`/market/products/${productId}`)); return; }
    if (!directTradeEnabled || !product?.purchasable || product.purchase_unit !== "hour") return;
    if (orderSubmissionInFlight.current) return;
    const pending = ensurePendingOrder();
    if (!pending) return;
    orderSubmissionInFlight.current = true;
    setConfirmOpen(false);
    setBusy(true);
    setError("");
    try {
      const result = await createDirectOrder(pending.input, pending.requestId);
      pendingOrderIntent.current = null;
      router.push(`/account/orders?order=${result.order.id}`);
    } catch (reason) {
      setError(reason instanceof ApiError && reason.status === 409
        ? `当前无法创建直接交易订单，请刷新服务状态或改为提交需求。${reason.message ? `（${reason.message}）` : ""}`
        : reason instanceof Error ? reason.message : "订单创建失败");
      orderSubmissionInFlight.current = false;
      setBusy(false);
    }
  }

  if (error && !product) return <div className="data-empty data-empty--error"><strong>{error}</strong><Link className="outline-link" href="/market">返回市场</Link></div>;
  if (!product) return <div className="data-empty">正在读取算力资源…</div>;
  const kaiSelfOperated = product.seller_type === "kai_self_operated" || product.market_source === "kai";
  const sellerName = localizeSupplierName(product.seller_name || product.supplier_name || product.source_name, locale);
  const fulfillmentLabel = product.fulfillment_mode === "merchant_manual" ? "商家人工交付 SSH" : "平台人工交付 SSH";
  const resourceClaimLabel = product.resource_claim_source === "merchant_declared" || (!product.resource_claim_source && !kaiSelfOperated)
    ? t("market.claim.merchant", "配置与库存由商家自行申报")
    : t("market.claim.kai", "商品信息由 KAI 发布");
  const sellerFacts = !kaiSelfOperated
    ? [product.supplier_id != null ? `ID ${product.supplier_id}` : "", product.supplier_rating != null ? t("market.rating", "评分 {rating}", { rating: product.supplier_rating.toFixed(1) }) : "", product.supplier_order_count != null ? t("market.completedOrders", "已完成 {count} 单", { count: product.supplier_order_count }) : ""].filter(Boolean).join(" · ")
    : "";
  const assuranceLabel = product.assurance_label || (kaiSelfOperated ? "KAI 自营 · 平台人工交付" : "商家发布 · 商家人工交付");
  const assuranceDescription = (kaiSelfOperated
    ? directTradeEnabled ? "商品与价格由 KAI 发布，平台安排人工交付。" : "商品信息由 KAI 发布，提交需求后由平台人工联系确认方案。"
    : directTradeEnabled ? "商品配置与库存由商家自行申报，并由该商家负责人工交付。" : "商品配置与库存由商家自行申报，提交需求后由对应商家人工联系确认方案。"
  );
  const purchaseHourOptions = product.purchase_hour_options.filter((hours) => Number.isInteger(hours) && hours >= 1 && hours <= 720);
  const hourPresets = purchaseHourOptions.length ? purchaseHourOptions : DEFAULT_PURCHASE_HOURS;
  const hourlyPurchase = product.purchase_unit === "hour";
  const unavailable = product.purchase_unavailable_reason || "当前资源暂不可下单";
  const resourceStatus = directTradeEnabled
    ? product.purchasable ? "库存有效，可从统一钱包下单" : unavailable
    : matchmakingEnabled && product.inquiry_available !== false ? "当前可提交需求" : "需求服务暂未开放";
  const inquiryLabel = !matchmakingEnabled || product.inquiry_available === false ? "需求服务暂未开放" : authLoading ? "正在确认账号…" : !user ? "登录后提交需求" : "提交需求";
  const purchaseLabel = !hourlyPurchase ? "该商品暂不支持小时购买" : authLoading ? "正在确认账号…" : !user ? "登录后下单" : !product.purchasable ? unavailable : busy ? "正在创建订单…" : "确认购买信息";

  return <><div className="product-detail-layout direct-product-detail">
    <section className="product-detail-main">
      <Link className="dossier-back" href="/market">返回算力市场</Link>
      <ProductImage className="product-detail-image" imageUrl={product.image_url} gpuModel={product.gpu_model} eager/>
      <p className="hero-eyebrow">{kaiSelfOperated ? "KAI SELF-OPERATED" : "MERCHANT LISTING"}</p>
      <h1>{product.gpu_model} <small>{product.memory}</small></h1>
      <p>{product.name} · {product.region} · {resourceStatus}</p>
      <div className="product-source"><ShieldCheck size={19}/><span>{kaiSelfOperated ? "卖方" : "商家"}：{product.supplier_id && !kaiSelfOperated ? <Link href={`/stores/${product.supplier_id}`}>{sellerName}</Link> : sellerName}{sellerFacts && <small>{sellerFacts}</small>}<small>{resourceClaimLabel} · {assuranceDescription}</small></span></div>
      <div className="direct-product-specs"><article><Cpu size={20}/><small>GPU</small><strong>{product.gpu_model} / {product.memory}</strong></article><article><HardDrives size={20}/><small>可用库存</small><strong>{product.available_quantity} 台</strong></article><article><TerminalWindow size={20}/><small>交付方式</small><strong>{fulfillmentLabel}</strong></article></div>
      <section className="direct-product-description"><h2>资源与使用说明</h2><p>{product.description || (kaiSelfOperated ? "KAI 暂未补充资源说明。" : "商家暂未补充资源说明。")}</p></section>
      {directTradeEnabled
        ? <div className="sandbox-disclosure"><ShieldCheck size={20}/><div><strong>{assuranceLabel} · 统一担保流程</strong><span>钱包卡时下单后先冻结；{kaiSelfOperated ? "平台履约人员" : "对应商家"}提交有效 SSH 信息，买家验收后结算。资源参数以交付验收结果为准，异常可在订单中发起争议。</span></div></div>
        : <div className="sandbox-disclosure"><ShieldCheck size={20}/><div><strong>{assuranceLabel} · 人工确认方案</strong><span>提交需求不会扣除卡时，也不会自动生成订单。工作人员将联系你确认资源配置、服务价格、交付时间与后续流程。</span></div></div>}
    </section>
    <aside className="purchase-panel direct-purchase-panel">
      <div><span>{directTradeEnabled ? "GPU 每小时价格" : "服务价格"}</span><strong>{directTradeEnabled ? `${product.unit_price_ch.toLocaleString("zh-CN", { maximumFractionDigits: 6 })} 卡时 / GPU·小时` : "询价"}</strong></div>
      <label>{directTradeEnabled ? "购买时长（小时）" : "预计使用时长（小时）"}<span className="product-hour-input"><button type="button" aria-label="减少一小时" disabled={purchaseHours <= 1} onClick={() => setPurchaseHours((value) => clampPurchaseHours(value - 1))}>−</button><input type="number" inputMode="numeric" min={1} max={720} step={1} value={purchaseHours} onChange={(event) => setPurchaseHours(Number(event.target.value))} onBlur={() => normalizeHours()} aria-label={`${directTradeEnabled ? "购买" : "预计使用"}时长，单位小时`}/><button type="button" aria-label="增加一小时" disabled={purchaseHours >= 720} onClick={() => setPurchaseHours((value) => clampPurchaseHours(value + 1))}>+</button></span><span className="cycle-grid">{hourPresets.map((hours) => <button className={purchaseHours === hours ? "active" : ""} type="button" onClick={() => setPurchaseHours(clampPurchaseHours(hours))} key={hours}>{hours} 小时</button>)}</span><small className="product-hour-hint">{directTradeEnabled ? "KAI 自营与商家新商品均按整数小时购买，可输入 1–720 小时。" : "填写预计需求即可，最终资源、时长和服务价格由人工联系确认。"}</small></label>
      <label>{directTradeEnabled ? "数量" : "需求数量"}<select value={quantity} onChange={(event) => setQuantity(Number(event.target.value))}>{Array.from({ length: directTradeEnabled ? Math.min(Math.max(product.available_quantity, 1), 10) : 10 }, (_, index) => index + 1).map((value) => <option value={value} key={value}>{value} 台</option>)}</select></label>
      <label>{directTradeEnabled ? "购买模式" : "服务方式"}<select value={directTradeEnabled ? purchaseType : "hourly"} disabled aria-label="当前服务方式"><option value={directTradeEnabled ? purchaseType : "hourly"}>{directTradeEnabled ? "使用（当前支持）" : "按小时算力服务"}</option></select><small className="product-hour-hint">{directTradeEnabled ? "持有资产与二级交易暂未开放，不会创建无法履约的订单。" : "当前仅收集需求，不在线支付、不自动扣款。"}</small></label>
      {directTradeEnabled && <><div className="purchase-total"><span>预计钱包扣款</span><strong>{walletTotal.toFixed(4)} 卡时</strong></div><div className="product-rebate-estimate"><span>{t("product.rebate.label", "预计到期个人购买返佣")}</span><strong>{rebateAmountText}</strong><small>{rebatePolicyText}</small></div></>}
      <button className="sandbox-purchase-button" type="button" disabled={directTradeEnabled ? !hourlyPurchase || busy || authLoading || Boolean(user && !product.purchasable) : authLoading || !matchmakingEnabled || product.inquiry_available === false} onClick={directTradeEnabled ? beginPurchase : beginInquiry}>{directTradeEnabled && hourlyPurchase && product.purchasable && user && !busy ? <Wallet size={17}/> : <CheckCircle size={17}/>} {directTradeEnabled ? purchaseLabel : inquiryLabel}</button>
      <p>{directTradeEnabled ? `卖方为 ${sellerName}，${fulfillmentLabel}。余额、冻结金额和订单状态均来自统一业务后端。` : `卖方为 ${sellerName}，${fulfillmentLabel}。提交后由人工联系确认配置、库存、价格和交付安排。`}</p>
      {error && <div className="commerce-error">{error}</div>}
    </aside>
  </div>{directTradeEnabled && confirmOpen && <div className="product-purchase-confirm-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) cancelPurchase(); }}><section className="product-purchase-confirm" role="dialog" aria-modal="true" aria-labelledby="product-purchase-confirm-title"><button type="button" className="product-purchase-confirm__close" aria-label="关闭购买确认" disabled={busy} onClick={cancelPurchase}><X size={18}/></button><p className="hero-eyebrow">ORDER CONFIRMATION</p><h2 id="product-purchase-confirm-title">确认小时购买</h2><p>{product.name}</p><dl><div><dt>卖方</dt><dd>{sellerName} · {fulfillmentLabel}</dd></div><div><dt>GPU / 数量</dt><dd>{product.gpu_model} × {quantity} 台</dd></div><div><dt>购买时长</dt><dd>{purchaseHours} 小时</dd></div><div><dt>购买模式</dt><dd>使用</dd></div><div><dt>钱包扣款</dt><dd>{walletTotal.toFixed(4)} 卡时</dd></div><div><dt>{t("product.rebate.label", "预计到期个人购买返佣")}</dt><dd>{rebateAmountText}</dd></div></dl><div className="product-purchase-confirm__actions"><button type="button" disabled={busy} onClick={cancelPurchase}>返回修改</button><button type="button" disabled={busy} onClick={() => void purchase()}>{busy ? "正在创建订单…" : "确认并下单"}</button></div><small>{t("product.rebate.settlement", "页面金额为预计值；确认交付时服务端会按个人等级和剩余额度最终重算，实际金额以资产到期结算为准。")}</small></section></div>}</>;
}
