"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle, Cpu, HardDrives, ShieldCheck, TerminalWindow, Wallet, X } from "@phosphor-icons/react";
import { ApiError, getCurrentUser, type AuthUser } from "@/lib/api";
import { createDirectOrder, getPublicProduct, type PublicProduct } from "@/lib/commerce-api";
import { loginHref } from "@/lib/auth-navigation";
import { ProductImage } from "@/components/product-image";
import { getUserRebate, listAvailableCoupons, type Coupon, type RebateSummary } from "@/lib/mobile-business-api";
import { clampPurchaseHours, estimateProductExpiryRebate, type ProductPurchaseType } from "@/lib/product-purchase";
import { useI18n } from "@/components/locale-root";
import { localizeMarketProductName, localizeMarketRegion, localizeSupplierName } from "@/lib/market-localization";
import { usePlatformCapabilities } from "@/lib/use-platform-capabilities";
import { directOrderIntentSignature, ensureDirectOrderIntent, type DirectOrderIntent } from "@/lib/web-business-contract";
import { normalizeInquiryRegionRequirement } from "@/lib/request-navigation";
import { formatCnySettlement } from "@/lib/display-currency";

const DEFAULT_PURCHASE_HOURS = [1, 6, 12, 24, 72, 168];

export function ProductDetail({ productId }: { productId: string }) {
  const router = useRouter();
  const { locale, displayCurrency, formatLedgerMoney, t } = useI18n();
  const { capabilities } = usePlatformCapabilities();
  const directTradeEnabled = capabilities.direct_trade_enabled === true;
  const holdingTradeEnabled = capabilities.holding_trade_enabled === true;
  const matchmakingEnabled = capabilities.matchmaking_enabled === true;
  const [product, setProduct] = useState<PublicProduct | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [rebate, setRebate] = useState<RebateSummary | null>(null);
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [selectedCouponId, setSelectedCouponId] = useState<number | null>(null);
  const [couponLoading, setCouponLoading] = useState(false);
  const [error, setError] = useState("");
  const [authLoading, setAuthLoading] = useState(true);
  const [purchaseHours, setPurchaseHours] = useState(24);
  const [quantity, setQuantity] = useState(1);
  const [purchaseType, setPurchaseType] = useState<ProductPurchaseType>("usage");
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

  const holdingModeAvailable = Boolean(
    holdingTradeEnabled
    && product
    && (product.seller_type === "kai_self_operated" || product.market_source === "kai"),
  );

  useEffect(() => {
    if (!holdingModeAvailable) setPurchaseType("usage");
  }, [holdingModeAvailable]);

  const walletTotal = useMemo(
    () => product ? product.unit_price_ch * purchaseHours * quantity : 0,
    [purchaseHours, product, quantity],
  );
  const selectedCoupon = useMemo(
    () => coupons.find((coupon) => coupon.id === selectedCouponId) || null,
    [coupons, selectedCouponId],
  );
  const couponDiscount = selectedCoupon ? Math.min(Number(selectedCoupon.amount || 0), walletTotal) : 0;
  const payableTotal = Math.max(0, walletTotal - couponDiscount);
  const rebateEstimate = useMemo(
    () => estimateProductExpiryRebate(walletTotal, purchaseType, rebate),
    [purchaseType, rebate, walletTotal],
  );
  const currentRebateRate = Number(rebate?.current_rate || 0);
  const minimumRebateOrder = Number(rebate?.minimum_order_amount || 0);
  const rebateCapRemaining = Number(rebate?.cap_remaining);
  const rebateCapKnown = Number.isFinite(rebateCapRemaining) && rebateCapRemaining >= 0;
  const walletMoney = formatLedgerMoney;
  const rebateAmountText = rebate?.rewards_enabled && rebateEstimate.ratePercent > 0
    ? t("product.rebate.amount", "+{amount}", { amount: walletMoney(rebateEstimate.amount) })
    : "—";
  const rebatePolicyText = purchaseType === "holding"
    ? t("product.holding.noRebate", "持有资产不参与个人购买返佣。")
    : !user
    ? t("product.rebate.login", "登录后读取个人等级返佣政策。")
    : !rebate
      ? t("product.rebate.unavailable", "暂时无法读取个人返佣政策，请稍后刷新。")
      : !rebate.rewards_enabled
        ? t("product.rebate.disabled", "个人购买返佣当前未开启。")
        : !rebateCapKnown
          ? t("product.rebate.unavailable", "暂时无法读取个人返佣政策，请稍后刷新。")
          : walletTotal < minimumRebateOrder
            ? t("product.rebate.minimum", "当前个人等级 {current}%；订单满 {amount} 后参与个人购买返佣。", { current: currentRebateRate, amount: walletMoney(minimumRebateOrder) })
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
      ...(selectedCouponId ? { coupon_id: selectedCouponId } : {}),
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
    setSelectedCouponId(null);
    setCoupons([]);
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

  async function beginPurchase() {
    if (!directTradeEnabled) return;
    if (!user) { router.push(loginHref(`/market/products/${productId}`)); return; }
    if (!product || (!product.purchasable && !(purchaseType === "holding" && holdingModeAvailable)) || product.purchase_unit !== "hour") return;
    const hours = clampPurchaseHours(purchaseHours);
    normalizeHours(hours);
    setCoupons([]);
    setSelectedCouponId(null);
    pendingOrderIntent.current = null;
    if (purchaseType === "usage") {
      setCouponLoading(true);
      try {
        setCoupons(await listAvailableCoupons(walletTotal, product.id, "usage"));
      } catch {
        setCoupons([]);
      } finally {
        setCouponLoading(false);
      }
    }
    ensurePendingOrder(hours);
    setConfirmOpen(true);
  }

  async function purchase() {
    if (!user) { router.push(loginHref(`/market/products/${productId}`)); return; }
    if (!directTradeEnabled || !product || (!product.purchasable && !(purchaseType === "holding" && holdingModeAvailable)) || product.purchase_unit !== "hour") return;
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
  const displayName = localizeMarketProductName(product.name, locale);
  const displayRegion = localizeMarketRegion(product.region, locale);
  const fulfillmentLabel = product.fulfillment_mode === "merchant_manual"
    ? t("product.fulfillment.merchantSsh", "商家人工交付 SSH")
    : t("product.fulfillment.platformSsh", "平台人工交付 SSH");
  const resourceClaimLabel = product.resource_claim_source === "merchant_declared" || (!product.resource_claim_source && !kaiSelfOperated)
    ? t("market.claim.merchant", "配置与库存由商家自行申报")
    : t("market.claim.kai", "商品信息由KAI星算发布");
  const sellerFacts = !kaiSelfOperated
    ? [product.supplier_id != null ? `ID ${product.supplier_id}` : "", product.supplier_rating != null ? t("market.rating", "评分 {rating}", { rating: product.supplier_rating.toFixed(1) }) : "", product.supplier_order_count != null ? t("market.completedOrders", "已完成 {count} 单", { count: product.supplier_order_count }) : ""].filter(Boolean).join(" · ")
    : "";
  const assuranceLabel = kaiSelfOperated
    ? t("market.assurance.kai", "KAI星算自营 · 平台人工交付")
    : t("market.assurance.merchant", "商家发布 · 商家人工交付");
  const assuranceDescription = (kaiSelfOperated
    ? directTradeEnabled ? t("product.assurance.kaiDirect", "商品与价格由KAI星算发布，平台安排人工交付。") : t("market.kai.assurance", "商品信息由KAI星算发布，提交需求后由平台人工联系确认方案。")
    : directTradeEnabled ? t("product.assurance.merchantDirect", "商品配置与库存由商家自行申报，并由该商家负责人工交付。") : t("market.merchant.assurance", "商品配置与库存由商家自行申报，提交需求后由对应商家人工联系确认方案。")
  );
  const purchaseHourOptions = product.purchase_hour_options.filter((hours) => Number.isInteger(hours) && hours >= 1 && hours <= 720);
  const hourPresets = purchaseHourOptions.length ? purchaseHourOptions : DEFAULT_PURCHASE_HOURS;
  const hourlyPurchase = product.purchase_unit === "hour";
  const directPurchaseAvailable = product.purchasable || (purchaseType === "holding" && holdingModeAvailable);
  const rawUnavailable = product.purchase_unavailable_reason || "";
  const unavailable = locale === "en" && /[\u3400-\u9fff]/.test(rawUnavailable)
    ? t("product.unavailable", "当前资源暂不可下单")
    : rawUnavailable || t("product.unavailable", "当前资源暂不可下单");
  const resourceStatus = directTradeEnabled
    ? product.purchasable ? t("product.available", "库存有效，可从统一钱包下单") : unavailable
    : matchmakingEnabled && product.inquiry_available !== false ? t("product.inquiryAvailable", "当前可提交需求") : t("product.inquiryUnavailable", "需求服务暂未开放");
  const inquiryLabel = !matchmakingEnabled || product.inquiry_available === false
    ? t("product.inquiryUnavailable", "需求服务暂未开放")
    : authLoading ? t("product.checkingAccount", "正在确认账号…") : !user ? t("product.loginToInquire", "登录后提交需求") : t("market.submitRequest", "提交需求");
  const purchaseLabel = !hourlyPurchase
    ? t("product.hourlyUnsupported", "该商品暂不支持小时购买")
    : authLoading ? t("product.checkingAccount", "正在确认账号…") : !user ? t("product.loginToBuy", "登录后下单") : !directPurchaseAvailable ? unavailable : busy ? t("product.confirm.creating", "正在创建订单…") : t("product.confirmInfo", "确认购买信息");

  return <><div className="product-detail-layout direct-product-detail">
    <section className="product-detail-main">
      <Link className="dossier-back" href="/market">{t("product.backToMarket", "返回算力市场")}</Link>
      <ProductImage className="product-detail-image" imageUrl={product.image_url} gpuModel={product.gpu_model} eager/>
      <p className="hero-eyebrow">{kaiSelfOperated ? "KAI星算 SELF-OPERATED" : "MERCHANT LISTING"}</p>
      <h1>{product.gpu_model} <small>{product.memory}</small></h1>
      <p>{displayName} · {displayRegion} · {resourceStatus}</p>
      <div className="product-source"><ShieldCheck size={19}/><span>{kaiSelfOperated ? t("product.seller", "卖方") : t("product.merchant", "商家")}：{product.supplier_id && !kaiSelfOperated ? <Link href={`/stores/${product.supplier_id}`}>{sellerName}</Link> : sellerName}{sellerFacts && <small>{sellerFacts}</small>}<small>{resourceClaimLabel} · {assuranceDescription}</small></span></div>
      <div className="direct-product-specs"><article><Cpu size={20}/><small>GPU</small><strong>{product.gpu_model} / {product.memory}</strong></article><article><HardDrives size={20}/><small>{t("market.stock", "可用库存")}</small><strong>{product.available_quantity} {t("market.units", "台")}</strong></article><article><TerminalWindow size={20}/><small>{t("market.fulfillment", "交付方式")}</small><strong>{fulfillmentLabel}</strong></article></div>
      <section className="direct-product-description"><h2>{t("product.resourceDescription", "资源与使用说明")}</h2><p>{product.description && !(locale === "en" && /[\u3400-\u9fff]/.test(product.description)) ? product.description : kaiSelfOperated ? t("product.kaiNoDescription", "KAI星算暂未补充资源说明。") : t("product.merchantNoDescription", "商家暂未补充资源说明。")}</p></section>
      {directTradeEnabled
        ? <div className="sandbox-disclosure"><ShieldCheck size={20}/><div><strong>{assuranceLabel} · {purchaseType === "holding" ? t("product.holding.rules", "持有资产规则") : t("product.guaranteeFlow", "统一担保流程")}</strong><span>{purchaseType === "holding" ? t("product.holding.risk", "按当前 KAI 自营报价立即登记持有资产；不提供 SSH 和使用收益，出售按最新有效行情结算到账户余额，价格波动可能产生亏损。") : t("product.guaranteeDescription", "订单金额下单后先冻结；{seller}提交有效 SSH 信息，买家验收后结算。资源参数以交付验收结果为准，异常可在订单中发起争议。", { seller: kaiSelfOperated ? t("product.platformFulfillmentStaff", "平台履约人员") : t("product.correspondingMerchant", "对应商家") })}</span></div></div>
        : <div className="sandbox-disclosure"><ShieldCheck size={20}/><div><strong>{assuranceLabel} · {t("product.manualPlan", "人工确认方案")}</strong><span>{t("product.manualPlanDescription", "提交需求不会扣除账户余额，也不会自动生成订单。工作人员将联系你确认资源配置、服务价格、交付时间与后续流程。")}</span></div></div>}
    </section>
    <aside className="purchase-panel direct-purchase-panel">
      <div><span>{directTradeEnabled ? t("product.hourlyPrice", "GPU 每小时价格") : t("market.servicePrice", "服务价格")}</span><strong>{directTradeEnabled ? `${walletMoney(product.unit_price_ch)} / ${locale === "en" ? "GPU·hour" : "GPU·小时"}` : t("market.inquiry", "询价")}</strong></div>
      <label>{directTradeEnabled ? t("product.duration.buy", "购买时长（小时）") : t("product.duration.estimate", "预计使用时长（小时）")}<span className="product-hour-input"><button type="button" aria-label={t("product.hour.decrease", "减少一小时")} disabled={purchaseHours <= 1} onClick={() => setPurchaseHours((value) => clampPurchaseHours(value - 1))}>−</button><input type="number" inputMode="numeric" min={1} max={720} step={1} value={purchaseHours} onChange={(event) => setPurchaseHours(Number(event.target.value))} onBlur={() => normalizeHours()} aria-label={t("product.duration.aria", "时长，单位小时")}/><button type="button" aria-label={t("product.hour.increase", "增加一小时")} disabled={purchaseHours >= 720} onClick={() => setPurchaseHours((value) => clampPurchaseHours(value + 1))}>+</button></span><span className="cycle-grid">{hourPresets.map((hours) => <button className={purchaseHours === hours ? "active" : ""} type="button" onClick={() => setPurchaseHours(clampPurchaseHours(hours))} key={hours}>{hours} {t("product.hours", "小时")}</button>)}</span><small className="product-hour-hint">{directTradeEnabled ? t("product.duration.directHint", "KAI星算自营与商家新商品均按整数小时购买，可输入 1–720 小时。") : t("product.duration.inquiryHint", "填写预计需求即可，最终资源、时长和服务价格由人工联系确认。")}</small></label>
      <label>{directTradeEnabled ? t("product.quantity", "数量") : t("product.requestQuantity", "需求数量")}<select value={quantity} onChange={(event) => setQuantity(Number(event.target.value))}>{Array.from({ length: directTradeEnabled ? Math.min(Math.max(product.available_quantity, 1), 10) : 10 }, (_, index) => index + 1).map((value) => <option value={value} key={value}>{value} {t("market.units", "台")}</option>)}</select></label>
      <label>{directTradeEnabled ? t("product.purchaseMode", "购买模式") : t("product.serviceMode", "服务方式")}<select value={directTradeEnabled ? purchaseType : "hourly"} disabled={!directTradeEnabled || !holdingModeAvailable} onChange={(event) => setPurchaseType(event.target.value as ProductPurchaseType)} aria-label={t("product.serviceMode.current", "当前服务方式")}><option value="usage">{t("product.mode.usage", "使用")}</option>{holdingModeAvailable && <option value="holding">{t("product.mode.holdingSellable", "持有并可出售")}</option>}{!directTradeEnabled && <option value="hourly">{t("product.mode.hourly", "按小时算力服务")}</option>}</select><small className="product-hour-hint">{directTradeEnabled ? purchaseType === "holding" ? t("product.holding.assetHint", "持有立即生成资产，可在个人资产按最新有效 KAI 行情出售。") : t("product.usage.assetHint", "使用模式在有效 SSH 交付并验收后生成使用资产。") : t("product.inquiry.noCharge", "当前仅收集需求，不在线支付、不自动扣款。")}</small></label>
      {directTradeEnabled && <><div className="purchase-total"><span>{t("product.walletTotal", "预计钱包扣款")}</span><strong>{walletMoney(walletTotal)}</strong></div><div className="product-rebate-estimate"><span>{t("product.rebate.label", "预计到期个人购买返佣")}</span><strong>{purchaseType === "holding" ? t("product.rebate.notEligible", "不参与") : rebateAmountText}</strong><small>{rebatePolicyText}</small></div></>}
      <button className="sandbox-purchase-button" type="button" disabled={directTradeEnabled ? !hourlyPurchase || busy || couponLoading || authLoading || Boolean(user && !directPurchaseAvailable) : authLoading || !matchmakingEnabled || product.inquiry_available === false} onClick={directTradeEnabled ? () => void beginPurchase() : beginInquiry}>{directTradeEnabled && hourlyPurchase && directPurchaseAvailable && user && !busy ? <Wallet size={17}/> : <CheckCircle size={17}/>} {directTradeEnabled ? couponLoading ? t("product.coupon.loading", "正在读取优惠券…") : purchaseLabel : inquiryLabel}</button>
      <p>{directTradeEnabled ? t("product.sellerDirectNotice", "卖方为 {seller}，{fulfillment}。余额、冻结金额和订单状态均来自统一业务后端。", { seller: sellerName, fulfillment: fulfillmentLabel }) : t("product.sellerInquiryNotice", "卖方为 {seller}，{fulfillment}。提交后由人工联系确认配置、库存、价格和交付安排。", { seller: sellerName, fulfillment: fulfillmentLabel })}</p>
      {error && <div className="commerce-error">{error}</div>}
    </aside>
  </div>{directTradeEnabled && confirmOpen && <div className="product-purchase-confirm-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) cancelPurchase(); }}><section className="product-purchase-confirm" role="dialog" aria-modal="true" aria-labelledby="product-purchase-confirm-title"><button type="button" className="product-purchase-confirm__close" aria-label={t("product.confirm.close", "关闭购买确认")} disabled={busy} onClick={cancelPurchase}><X size={18}/></button><p className="hero-eyebrow">ORDER CONFIRMATION</p><h2 id="product-purchase-confirm-title">{t("product.confirm.title", "确认{mode}购买", { mode: purchaseType === "holding" ? t("product.mode.holding", "持有") : t("product.mode.usage", "使用") })}</h2><p>{displayName}</p><dl><div><dt>{t("product.seller", "卖方")}</dt><dd>{sellerName} · {purchaseType === "holding" ? t("product.holding.registration", "平台持有资产登记") : fulfillmentLabel}</dd></div><div><dt>{t("product.gpuQuantity", "GPU / 数量")}</dt><dd>{product.gpu_model} × {quantity} {t("market.units", "台")}</dd></div><div><dt>{t("product.purchaseHours", "购买时长")}</dt><dd>{purchaseHours} GPU {t("product.hours", "小时")}</dd></div><div><dt>{t("product.purchaseMode", "购买模式")}</dt><dd>{purchaseType === "holding" ? t("product.mode.holdingSellable", "持有并可出售") : t("product.mode.usage", "使用")}</dd></div>{purchaseType === "usage" && <div><dt>{t("product.coupon.select", "优惠券")}</dt><dd><select className="product-coupon-select" value={selectedCouponId ?? ""} onChange={(event) => { setSelectedCouponId(event.target.value ? Number(event.target.value) : null); pendingOrderIntent.current = null; }}><option value="">{t("product.coupon.none", "不使用优惠券")}</option>{coupons.map((coupon) => <option value={coupon.id} key={coupon.id}>{coupon.name} · -{walletMoney(Math.min(coupon.amount, walletTotal))}</option>)}</select></dd></div>}<div><dt>{t("product.orderGross", "订单原价")}</dt><dd>{walletMoney(walletTotal)}</dd></div>{selectedCoupon && <div><dt>{t("product.coupon.discount", "优惠券抵扣")}</dt><dd>-{walletMoney(couponDiscount)}</dd></div>}{displayCurrency !== "CNY" && <div><dt>{t("product.displayReference", "{currency} 参考金额", { currency: displayCurrency })}</dt><dd>{walletMoney(payableTotal)}</dd></div>}<div><dt>{t("product.cnySettlement", "实际人民币结算")}</dt><dd><strong>{formatCnySettlement(payableTotal)}</strong></dd></div>{purchaseType === "usage" && <div><dt>{t("product.rebate.label", "预计到期个人购买返佣")}</dt><dd>{rebateAmountText}</dd></div>}</dl><div className="product-purchase-confirm__actions"><button type="button" disabled={busy} onClick={cancelPurchase}>{t("product.confirm.back", "返回修改")}</button><button type="button" disabled={busy} onClick={() => void purchase()}>{busy ? t("product.confirm.creating", "正在创建订单…") : t("product.confirm.submit", "确认并下单")}</button></div><small>{displayCurrency !== "CNY" && <>{t("product.currencyNotice", "{currency} 金额仅供参考，钱包实际扣款及订单结算固定使用人民币。", { currency: displayCurrency })} </>}{purchaseType === "holding" ? t("product.holding.confirmNotice", "持有资产不提供 SSH 使用、使用收益或购买返佣；出售按最新有效 KAI 行情结算为人民币。") : t("product.rebate.settlement", "页面金额为预计值；确认交付时服务端会按个人等级和剩余额度最终重算，实际金额以资产到期结算为准。")}</small></section></div>}</>;
}
