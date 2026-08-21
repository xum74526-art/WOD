"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle, Cpu, HardDrives, ShieldCheck, TerminalWindow, Wallet } from "@phosphor-icons/react";
import { ApiError, getCurrentUser, type AuthUser } from "@/lib/api";
import { createDirectOrder, getPublicProduct, type PublicProduct } from "@/lib/commerce-api";
import { formatMoney } from "@/lib/commerce-ui";
import { loginHref } from "@/lib/auth-navigation";

function cycleLabel(days: number) {
  if (days % 30 === 0) return `${days / 30} 个月`;
  return `${days} 天`;
}

export function ProductDetail({ productId }: { productId: string }) {
  const router = useRouter();
  const [product, setProduct] = useState<PublicProduct | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState("");
  const [authLoading, setAuthLoading] = useState(true);
  const [cycleDays, setCycleDays] = useState(30);
  const [quantity, setQuantity] = useState(1);
  const [purchaseType, setPurchaseType] = useState<"usage" | "holding">("usage");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getPublicProduct(Number(productId))
      .then((payload) => {
        setProduct(payload.data);
        setCycleDays(payload.data.cycle[0] || 30);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "算力资源读取失败"));
    getCurrentUser()
      .then(({ user: current }) => setUser(current))
      .catch(() => setUser(null))
      .finally(() => setAuthLoading(false));
  }, [productId]);

  const total = useMemo(
    () => product ? Number(product.price.amount) * cycleDays * 24 * quantity : 0,
    [cycleDays, product, quantity],
  );

  async function purchase() {
    if (!user) { router.push(loginHref(`/market/products/${productId}`)); return; }
    if (!product?.purchasable) return;
    setBusy(true); setError("");
    try {
      const result = await createDirectOrder({
        product_id: product.id,
        quantity,
        cycle_days: cycleDays,
        purchase_type: purchaseType,
      });
      router.push(`/account/orders?order=${result.order.id}`);
    } catch (reason) {
      setError(reason instanceof ApiError || reason instanceof Error ? reason.message : "订单创建失败");
      setBusy(false);
    }
  }

  if (error && !product) return <div className="data-empty data-empty--error"><strong>{error}</strong><Link className="outline-link" href="/market">返回市场</Link></div>;
  if (!product) return <div className="data-empty">正在读取手机端算力资源…</div>;
  const unavailable = product.purchase_unavailable_reason || "当前资源暂不可下单";
  const purchaseLabel = authLoading ? "正在确认账号…" : !user ? "登录后下单" : !product.purchasable ? unavailable : busy ? "正在创建订单…" : "使用钱包余额下单";

  return <div className="product-detail-layout direct-product-detail">
    <section className="product-detail-main">
      <Link className="dossier-back" href="/market">返回算力市场</Link>
      <p className="hero-eyebrow">WOD MOBILE BACKEND / SHARED DATA</p>
      <h1>{product.gpu_model} <small>{product.memory}</small></h1>
      <p>{product.name} · {product.region} · {product.purchasable ? "库存有效，可从共享钱包下单" : unavailable}</p>
      <div className="product-source"><ShieldCheck size={19}/><span>数据来源：{product.source_name || "WOD 手机端后端"}<small>Web 与 App 共用商品、库存、钱包、订单和交付状态，不再维护 Web 独立副本。</small></span></div>
      <div className="direct-product-specs"><article><Cpu size={20}/><small>GPU</small><strong>{product.gpu_model} / {product.memory}</strong></article><article><HardDrives size={20}/><small>可用库存</small><strong>{product.available_quantity} 台</strong></article><article><TerminalWindow size={20}/><small>交付方式</small><strong>商家人工交付 SSH</strong></article></div>
      <section className="direct-product-description"><h2>资源与使用说明</h2><p>{product.description || "商家暂未补充资源说明。"}</p></section>
      <div className="sandbox-disclosure"><ShieldCheck size={20}/><div><strong>手机端统一交付流程</strong><span>钱包金额下单后先冻结；商家填写有效 SSH 信息，买家确认交付后订单完成并生成资产。Web 不保存另一套订单或余额。</span></div></div>
    </section>
    <aside className="purchase-panel direct-purchase-panel">
      <div><span>GPU 每小时价格</span><strong>{formatMoney(product.price.amount, product.price.currency, product.price.unit)}</strong></div>
      <label>购买周期<span className="cycle-grid">{product.cycle.map((days) => <button className={cycleDays === days ? "active" : ""} type="button" onClick={() => setCycleDays(days)} key={days}>{cycleLabel(days)}</button>)}</span></label>
      <label>数量<select value={quantity} onChange={(event) => setQuantity(Number(event.target.value))}>{Array.from({ length: Math.min(Math.max(product.available_quantity, 1), 10) }, (_, index) => index + 1).map((value) => <option value={value} key={value}>{value} 台</option>)}</select></label>
      <label>购买模式<select value={purchaseType} onChange={(event) => setPurchaseType(event.target.value as "usage" | "holding")}><option value="usage">使用</option><option value="holding">持有（测试）</option></select></label>
      <div className="purchase-total"><span>预计订单总额</span><strong>{total.toFixed(2)} CNY</strong></div>
      <button className="sandbox-purchase-button" type="button" disabled={busy || authLoading || Boolean(user && !product.purchasable)} onClick={() => void purchase()}>{product.purchasable && user && !busy ? <Wallet size={17}/> : <CheckCircle size={17}/>} {purchaseLabel}</button>
      <p>余额、冻结金额和订单都来自手机端 SQLite。余额不足时请先在手机端已接入的充值流程中处理。</p>
      {error && <div className="commerce-error">{error}</div>}
    </aside>
  </div>;
}
