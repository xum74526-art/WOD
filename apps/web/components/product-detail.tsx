"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle, Cpu, HardDrives, ShieldCheck, TerminalWindow, Wallet, X } from "@phosphor-icons/react";
import { ApiError, apiRequest, getCurrentUser, type AuthUser } from "@/lib/api";
import { createDirectOrder, getPublicProduct, type PublicProduct } from "@/lib/commerce-api";
import { loginHref } from "@/lib/auth-navigation";
import { canonicalApiPath } from "@/lib/canonical-api";
import { ProductImage } from "@/components/product-image";
import {
  clampPurchaseHours,
  estimateProductExpiryRebate,
  type ProductPurchaseType,
  type ProductRebateSummary,
} from "@/lib/product-purchase";

const DEFAULT_PURCHASE_HOURS = [1, 6, 12, 24, 72, 168];

export function ProductDetail({ productId }: { productId: string }) {
  const router = useRouter();
  const [product, setProduct] = useState<PublicProduct | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState("");
  const [authLoading, setAuthLoading] = useState(true);
  const [purchaseHours, setPurchaseHours] = useState(24);
  const [quantity, setQuantity] = useState(1);
  const [purchaseType, setPurchaseType] = useState<ProductPurchaseType>("usage");
  const [rebate, setRebate] = useState<ProductRebateSummary | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);

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
      .then(({ user: current }) => {
        setUser(current);
        return apiRequest<ProductRebateSummary>(canonicalApiPath("/user/rebate"))
          .then(setRebate)
          .catch(() => setRebate(null));
      })
      .catch(() => setUser(null))
      .finally(() => setAuthLoading(false));
  }, [productId]);

  const walletTotal = useMemo(
    () => product ? product.unit_price_ch * purchaseHours * quantity : 0,
    [purchaseHours, product, quantity],
  );
  const rebateEstimate = useMemo(
    () => estimateProductExpiryRebate(walletTotal, purchaseType, rebate),
    [purchaseType, rebate, walletTotal],
  );

  function normalizeHours(value = purchaseHours) {
    setPurchaseHours(clampPurchaseHours(value));
  }

  function beginPurchase() {
    if (!user) { router.push(loginHref(`/market/products/${productId}`)); return; }
    if (!product?.purchasable || product.market_source !== "kai" || product.purchase_unit !== "hour") return;
    normalizeHours();
    setConfirmOpen(true);
  }

  async function purchase() {
    if (!user) { router.push(loginHref(`/market/products/${productId}`)); return; }
    if (!product?.purchasable || product.market_source !== "kai" || product.purchase_unit !== "hour") return;
    setConfirmOpen(false);
    setBusy(true); setError("");
    try {
      const result = await createDirectOrder({
        product_id: product.id,
        quantity,
        hours: purchaseHours,
        purchase_type: purchaseType,
      });
      router.push(`/account/orders?order=${result.order.id}`);
    } catch (reason) {
      setError(reason instanceof ApiError || reason instanceof Error ? reason.message : "订单创建失败");
      setBusy(false);
    }
  }

  if (error && !product) return <div className="data-empty data-empty--error"><strong>{error}</strong><Link className="outline-link" href="/market">返回市场</Link></div>;
  if (!product) return <div className="data-empty">正在读取算力资源…</div>;
  const hourlyPurchase = product.market_source === "kai" && product.purchase_unit === "hour";
  const purchaseHourOptions = product.purchase_hour_options.filter((hours) => Number.isInteger(hours) && hours >= 1 && hours <= 720);
  const hourPresets = purchaseHourOptions.length ? purchaseHourOptions : DEFAULT_PURCHASE_HOURS;
  const unavailable = product.purchase_unavailable_reason || "当前资源暂不可下单";
  const purchaseLabel = !hourlyPurchase ? "该历史商品不支持新购" : authLoading ? "正在确认账号…" : !user ? "登录后下单" : !product.purchasable ? unavailable : busy ? "正在创建订单…" : "确认购买信息";

  return <><div className="product-detail-layout direct-product-detail">
    <section className="product-detail-main">
      <Link className="dossier-back" href="/market">返回算力市场</Link>
      <ProductImage className="product-detail-image" imageUrl={product.image_url} gpuModel={product.gpu_model} eager/>
      <p className="hero-eyebrow">KAI PRICING / SHARED DATA</p>
      <h1>{product.gpu_model} <small>{product.memory}</small></h1>
      <p>{product.name} · {product.region} · {product.purchasable ? "库存有效，可从共享钱包下单" : unavailable}</p>
      <div className="product-source"><ShieldCheck size={19}/><span>数据来源：{product.source_name || "KAI Pricing"}<small>Web、iOS 与 Android 共用商品、库存、钱包、订单和交付状态。</small></span></div>
      <div className="direct-product-specs"><article><Cpu size={20}/><small>GPU</small><strong>{product.gpu_model} / {product.memory}</strong></article><article><HardDrives size={20}/><small>可用库存</small><strong>{product.available_quantity} 台</strong></article><article><TerminalWindow size={20}/><small>交付方式</small><strong>商家人工交付 SSH</strong></article></div>
      <section className="direct-product-description"><h2>资源与使用说明</h2><p>{product.description || "商家暂未补充资源说明。"}</p></section>
      <div className="sandbox-disclosure"><ShieldCheck size={20}/><div><strong>统一交付流程</strong><span>钱包金额下单后先冻结；商家填写有效 SSH 信息，买家确认交付后订单完成并生成资产。</span></div></div>
    </section>
    <aside className="purchase-panel direct-purchase-panel">
      <div><span>GPU 每小时价格</span><strong>{product.unit_price_ch.toLocaleString("zh-CN", { maximumFractionDigits: 6 })} 卡时 / GPU·小时</strong></div>
      <label>购买时长（小时）{hourlyPurchase ? <><span className="product-hour-input"><button type="button" aria-label="减少一小时" disabled={purchaseHours <= 1} onClick={() => setPurchaseHours((value) => clampPurchaseHours(value - 1))}>−</button><input type="number" inputMode="numeric" min={1} max={720} step={1} value={purchaseHours} onChange={(event) => setPurchaseHours(Number(event.target.value))} onBlur={() => normalizeHours()} aria-label="购买时长，单位小时"/><button type="button" aria-label="增加一小时" disabled={purchaseHours >= 720} onClick={() => setPurchaseHours((value) => clampPurchaseHours(value + 1))}>+</button></span><span className="cycle-grid">{hourPresets.map((hours) => <button className={purchaseHours === hours ? "active" : ""} type="button" onClick={() => setPurchaseHours(clampPurchaseHours(hours))} key={hours}>{hours} 小时</button>)}</span><small className="product-hour-hint">新 KAI 商品仅按整数小时购买，可输入 1–720 小时。</small></> : <small>仅保留历史展示，不接受新订单</small>}</label>
      <label>数量<select value={quantity} onChange={(event) => setQuantity(Number(event.target.value))}>{Array.from({ length: Math.min(Math.max(product.available_quantity, 1), 10) }, (_, index) => index + 1).map((value) => <option value={value} key={value}>{value} 台</option>)}</select></label>
      <label>购买模式<select value={purchaseType} onChange={(event) => setPurchaseType(event.target.value as ProductPurchaseType)}><option value="usage">使用</option><option value="holding">持有资产</option></select></label>
      <div className="purchase-total"><span>预计钱包扣款</span><strong>{walletTotal.toFixed(4)} 卡时</strong></div>
      <div className="product-rebate-estimate"><span>到期预计返佣</span><strong>+{rebateEstimate.amount.toFixed(2)} 卡时</strong><small>{purchaseType === "holding" ? "持有资产不参与到期返佣" : !user ? "登录后读取返佣政策" : !rebate?.rewards_enabled ? "返佣计划当前未开启" : `按预计 ${rebateEstimate.ratePercent.toFixed(2)}% 计算，实际以到期结算为准`}</small></div>
      <button className="sandbox-purchase-button" type="button" disabled={!hourlyPurchase || busy || authLoading || Boolean(user && !product.purchasable)} onClick={beginPurchase}>{hourlyPurchase && product.purchasable && user && !busy ? <Wallet size={17}/> : <CheckCircle size={17}/>} {purchaseLabel}</button>
      <p>余额、冻结金额和订单都来自统一业务后端。余额不足时可前往钱包使用七相支付充值。</p>
      {error && <div className="commerce-error">{error}</div>}
    </aside>
  </div>{confirmOpen && <div className="product-purchase-confirm-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setConfirmOpen(false); }}><section className="product-purchase-confirm" role="dialog" aria-modal="true" aria-labelledby="product-purchase-confirm-title"><button type="button" className="product-purchase-confirm__close" aria-label="关闭购买确认" disabled={busy} onClick={() => setConfirmOpen(false)}><X size={18}/></button><p className="hero-eyebrow">ORDER CONFIRMATION</p><h2 id="product-purchase-confirm-title">确认小时购买</h2><p>{product.name}</p><dl><div><dt>GPU / 数量</dt><dd>{product.gpu_model} × {quantity} 台</dd></div><div><dt>购买时长</dt><dd>{purchaseHours} 小时</dd></div><div><dt>购买模式</dt><dd>{purchaseType === "usage" ? "使用" : "持有资产"}</dd></div><div><dt>钱包扣款</dt><dd>{walletTotal.toFixed(4)} 卡时</dd></div>{purchaseType === "usage" && <div><dt>到期预计返佣</dt><dd>+{rebateEstimate.amount.toFixed(2)} 卡时</dd></div>}</dl><div className="product-purchase-confirm__actions"><button type="button" disabled={busy} onClick={() => setConfirmOpen(false)}>返回修改</button><button type="button" disabled={busy} onClick={() => void purchase()}>{busy ? "正在创建订单…" : "确认并下单"}</button></div><small>订单按小时计费；返佣以资产到期后的服务端实际结算结果为准。</small></section></div>}</>;
}
