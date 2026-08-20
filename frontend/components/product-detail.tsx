"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle, Cpu, HardDrives, Key, ShieldCheck, TerminalWindow } from "@phosphor-icons/react";
import { ApiError, getCurrentUser, type AuthUser } from "@/lib/api";
import { createDirectOrder, getPublicProduct, listSshKeys, type PublicProduct, type SshKey } from "@/lib/commerce-api";
import { formatMoney } from "@/lib/commerce-ui";
import { loginHref } from "@/lib/auth-navigation";

const durations = [1, 6, 12, 24, 72, 168, 720];

function durationLabel(hours: number) {
  if (hours === 720) return "30 天";
  if (hours === 168) return "7 天";
  if (hours === 72) return "3 天";
  if (hours === 24) return "1 天";
  return `${hours} 小时`;
}

export function ProductDetail({ productId }: { productId: string }) {
  const router = useRouter();
  const [product, setProduct] = useState<PublicProduct | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [keys, setKeys] = useState<SshKey[]>([]);
  const [keyId, setKeyId] = useState(0);
  const [error, setError] = useState("");
  const [authLoading, setAuthLoading] = useState(true);
  const [durationHours, setDurationHours] = useState(24);
  const [paymentChannel, setPaymentChannel] = useState("alipay_pc_direct");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getPublicProduct(Number(productId))
      .then((payload) => setProduct(payload.data))
      .catch((reason) => setError(reason instanceof Error ? reason.message : "服务器读取失败"));
    getCurrentUser().then(async ({ user: current }) => {
      setUser(current);
      if (current.role === "personal") {
        const payload = await listSshKeys();
        const active = payload.data.filter((item) => item.status === "active");
        setKeys(active);
        setKeyId(active[0]?.id || 0);
      }
    }).catch(() => setUser(null)).finally(() => setAuthLoading(false));
  }, [productId]);

  async function purchase() {
    if (!user) { router.push(loginHref(`/market/products/${productId}`)); return; }
    if (!product || user.role !== "personal" || !product.server_online || !keyId) return;
    setBusy(true); setError("");
    try {
      const result = await createDirectOrder({
        product_id: product.id,
        ssh_key_id: keyId,
        duration_hours: durationHours,
        payment_channel: paymentChannel,
      });
      if (result.payment?.checkout_url) {
        window.location.assign(result.payment.checkout_url);
        return;
      }
      router.push(`/account/leases?lease=${result.lease.id}`);
    } catch (reason) {
      setError(reason instanceof ApiError || reason instanceof Error ? reason.message : "服务器租赁创建失败");
      setBusy(false);
    }
  }

  if (error && !product) return <div className="data-empty data-empty--error"><strong>{error}</strong><Link className="outline-link" href="/market">返回市场</Link></div>;
  if (!product) return <div className="data-empty">正在读取商家服务器…</div>;
  const total = Number(product.price.amount) * durationHours;
  const managementAction = user?.role === "supplier"
    ? { href: "/supplier/resources", role: "商家账号", label: "进入服务器管理", description: "商家账号负责登记服务器、安装 Agent、上架商品和查看租约，不参与买家租用流程。" }
    : user?.role === "admin"
      ? { href: "/admin/resources", role: "管理员账号", label: "进入服务器审核", description: "管理员账号负责审核服务器与 Agent 状态，不参与买家租用流程。" }
      : null;
  const purchaseLabel = !user
    ? "登录后租用服务器"
    : user.role !== "personal"
      ? "仅买家账号可购买"
      : !product.server_online
        ? "服务器当前不可租用"
        : !keyId
          ? "请先添加 SSH 公钥"
          : busy ? "正在创建访问租约…" : "付款并获取 SSH 权限";

  return <div className="product-detail-layout direct-product-detail">
    <section className="product-detail-main">
      <Link className="dossier-back" href="/market">返回服务器市场</Link>
      <p className="hero-eyebrow">DEDICATED SERVER / VERIFIED MERCHANT</p>
      <h1>{product.gpu_model} <small>{product.memory}</small></h1>
      <p>{product.name} · {product.region} · {product.server_online ? "Agent 在线，可立即租用" : "服务器暂时离线"}</p>
      <div className="product-source"><ShieldCheck size={19}/><span>已审核商家：{product.source_name || "平台商家"}<small>平台只负责交易、租期和 SSH 公钥授权，不接触你的私钥。</small></span></div>
      <div className="direct-product-specs"><article><Cpu size={20}/><small>CPU / 内存</small><strong>{product.cpu_cores || "—"} 核 / {product.ram_gb || "—"} GB</strong></article><article><HardDrives size={20}/><small>磁盘 / 带宽</small><strong>{product.disk_gb || "—"} GB / {product.bandwidth_mbps || "—"} Mbps</strong></article><article><TerminalWindow size={20}/><small>交付方式</small><strong>SSH 公钥自动授权</strong></article></div>
      <section className="direct-product-description"><h2>服务器与使用说明</h2><p>{product.description || "商家暂未补充服务器说明。"}</p></section>
      <div className="sandbox-disclosure"><Key size={20}/><div><strong>买家自己的 SSH 公钥</strong><span>付款后，Agent 将你的公钥写入独立租户账号并返回 SSH 命令；到期立即撤销访问，保留 2 小时续费宽限期。</span></div></div>
    </section>
    {authLoading ? <aside className="purchase-panel direct-purchase-panel role-management-panel">
      <div><span>账号身份</span><strong>正在确认…</strong></div>
      <div className="role-management-panel__notice"><ShieldCheck size={20}/><span><strong>正在读取账号权限</strong><small>确认买家、商家或管理员身份后显示对应操作。</small></span></div>
    </aside> : managementAction ? <aside className="purchase-panel direct-purchase-panel role-management-panel">
      <div><span>当前身份</span><strong>{managementAction.role}</strong></div>
      <div className="role-management-panel__notice"><ShieldCheck size={20}/><span><strong>此账号不能租用服务器</strong><small>{managementAction.description}</small></span></div>
      <Link className="sandbox-purchase-button" href={managementAction.href}>{managementAction.label}</Link>
      <Link className="role-management-panel__back" href="/market">返回公开市场</Link>
    </aside> : <aside className="purchase-panel direct-purchase-panel">
      <div><span>服务器小时价格</span><strong>{formatMoney(product.price.amount, product.price.currency, product.price.unit)}</strong></div>
      <label>租用时长<span className="cycle-grid">{durations.map((hours) => <button className={durationHours === hours ? "active" : ""} type="button" onClick={() => setDurationHours(hours)} key={hours}>{durationLabel(hours)}</button>)}</span></label>
      {user?.role === "personal" && <label>登录公钥{keys.length ? <select value={keyId} onChange={(event) => setKeyId(Number(event.target.value))}>{keys.map((item) => <option value={item.id} key={item.id}>{item.name} · {item.fingerprint.slice(0, 22)}…</option>)}</select> : <span className="ssh-key-required"><Key size={16}/><span>还没有可用公钥</span><Link href="/account/ssh-keys">添加 SSH 公钥</Link></span>}</label>}
      {user?.role === "personal" && <label>支付方式<select value={paymentChannel} onChange={(event) => setPaymentChannel(event.target.value)}><option value="alipay_pc_direct">支付宝电脑支付</option><option value="alipay_wap">支付宝手机支付</option><option value="wx_wap">微信 H5 支付</option><option value="upacp_pc">银联网关支付</option></select></label>}
      <div className="purchase-total"><span>订单总额</span><strong>{total.toFixed(2)} {product.price.currency}</strong></div>
      <button className="sandbox-purchase-button" type="button" disabled={busy || Boolean(user && user.role !== "personal") || !product.server_online || Boolean(user?.role === "personal" && !keyId)} onClick={() => void purchase()}>{product.server_online && keyId && !busy ? <CheckCircle size={17}/> : <ShieldCheck size={17}/>} {purchaseLabel}</button>
      <p>Ping++ Test 环境使用官方模拟支付页且不产生真实资金；Live 环境调用已开通渠道。服务端验签并查单成功后才下发 SSH 公钥。</p>
      {error && <div className="commerce-error">{error}</div>}
    </aside>}
  </div>;
}
