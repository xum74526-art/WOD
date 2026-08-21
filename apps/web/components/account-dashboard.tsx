"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Bank, Bell, Gift, HardDrives, Receipt, Ticket, TrendUp, Wallet } from "@phosphor-icons/react";
import { apiBaseUrl, readApiError } from "@/lib/api";
import { useI18n } from "@/components/locale-root";

type Summary = {
  user: { display_name: string; email?: string; email_verified: boolean; role: "personal" | "supplier" | "admin" };
  metrics: { active_orders: number; active_assets: number; hosted_devices: number; open_requests: number };
  supplier_status: string;
  services: { payment: boolean; kyc: boolean };
};

export function AccountDashboard() {
  const { locale, t } = useI18n();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiBaseUrl}/api/v1/account/summary`, { credentials: "include", cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(await readApiError(response));
        return response.json();
      })
      .then((payload) => setSummary(payload.data))
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "账户服务暂时不可用");
      });
    return () => controller.abort();
  }, []);

  if (error) return <section className="workspace-page"><div className="workspace-state workspace-state--error"><div><strong>{error}</strong><span>登录后可查看独立网站账户数据。</span><Link className="primary-link" href="/login">前往登录</Link></div></div></section>;
  if (!summary) return <section className="workspace-page"><div className="workspace-skeleton" aria-label="正在加载账户数据" /></section>;

  const metrics = [
    [locale === "en" ? "Active orders" : "进行中订单", summary.metrics.active_orders, Receipt],
    [locale === "en" ? "Running compute assets" : "运行中算力资产", summary.metrics.active_assets, HardDrives],
  ] as const;
  return (
    <section className="workspace-page">
      <div className="workspace-page__head"><p>MOBILE DATA OVERVIEW</p><h1>{t("account.welcome", "{name}，欢迎回来", { name: summary.user.display_name })}</h1><span>{t("account.sameData", "此处数据与手机端账号实时共用")}</span></div>
      <div className="metric-strip">{metrics.map(([label, value, Icon]) => <div key={label}><Icon size={19} /><span>{label}</span><strong>{value}</strong></div>)}</div>
      <section className="workspace-action-list">
        <h2>{t("account.next", "接下来")}</h2>
        <Link href="/market"><span><strong>{locale === "en" ? "Browse shared compute" : "浏览共享算力资源"}</strong><small>{locale === "en" ? "Products, stock, and prices come directly from the mobile backend" : "商品、库存和价格直接读取手机端后端"}</small></span><ArrowRight size={18}/></Link>
        <Link href="/account/assets"><span><strong>{locale === "en" ? "Manage assets" : "管理个人资产"}</strong><small>{locale === "en" ? "Review purchased compute, earnings, status, and expiry" : "查看已购算力、收益、状态和到期时间"}</small></span><HardDrives size={18}/></Link>
        <Link href="/account/orders"><span><strong>{t("nav.orders", "查看我的订单")}</strong><small>{locale === "en" ? "Track payment, SSH delivery, and buyer confirmation" : "跟踪冻结、SSH 交付与买家确认状态"}</small></span><Receipt size={18}/></Link>
        <Link href="/account/wallet"><span><strong>{locale === "en" ? "Open shared wallet" : "查看共享钱包"}</strong><small>{locale === "en" ? "Balance and ledger are identical to the App" : "余额和账本与 App 完全一致"}</small></span><Wallet size={18}/></Link>
        <Link href="/account/revenue"><span><strong>{locale === "en" ? "Earnings & rebates" : "收益与返佣"}</strong><small>{locale === "en" ? "Review trends, earnings records, and rebate tiers" : "查看趋势、收益记录和返佣阶梯"}</small></span><TrendUp size={18}/></Link>
        <Link href="/account/bank-accounts"><span><strong>{locale === "en" ? "Bank cards & settlement" : "银行卡与结算"}</strong><small>{locale === "en" ? "Manage verified bank cards used for withdrawals" : "管理提现使用的实名银行卡"}</small></span><Bank size={18}/></Link>
        <Link href="/account/coupons"><span><strong>{locale === "en" ? "Coupons" : "优惠券"}</strong><small>{locale === "en" ? "View available offers and redeem a code" : "查看可用优惠并兑换新券"}</small></span><Ticket size={18}/></Link>
        <Link href="/account/referrals"><span><strong>{locale === "en" ? "Referral records" : "邀请记录"}</strong><small>{locale === "en" ? "Manage invitation codes and confirmed rewards" : "管理邀请码和后端确认的奖励"}</small></span><Gift size={18}/></Link>
        <Link href="/account/notifications"><span><strong>{locale === "en" ? "Notifications" : "站内通知"}</strong><small>{locale === "en" ? "Read the same notification center as the mobile App" : "读取手机端通知中心的数据"}</small></span><Bell size={18}/></Link>
        {summary.user.role === "supplier"
          ? <Link href="/supplier"><span><strong>{locale === "en" ? "Back to Supplier Console" : "返回商家后台"}</strong><small>{locale === "en" ? "Quotes, resources, and delivery are managed in the supplier console" : "报价、资源和交付统一在商家后台处理"}</small></span><ArrowRight size={18}/></Link>
          : <Link href="/supplier/apply"><span><strong>{t("home.cta.action", "申请成为商家")}</strong><small>{locale === "en" ? `Current status: ${summary.supplier_status}` : `当前状态：${summary.supplier_status}`}</small></span><ArrowRight size={18}/></Link>}
      </section>
      {!summary.services.payment && <div className="workspace-service-note">{locale === "en" ? "Mobile payment service is currently disabled. Web does not provide a separate recharge flow or simulated balance." : "手机端支付服务当前未启用；Web 不提供独立充值或模拟余额。"}</div>}
    </section>
  );
}
