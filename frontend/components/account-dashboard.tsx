"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, HardDrives, Key, Receipt } from "@phosphor-icons/react";
import { apiBaseUrl, readApiError } from "@/lib/api";

type Summary = {
  user: { display_name: string; email?: string; email_verified: boolean; role: "personal" | "supplier" | "admin" };
  metrics: { active_orders: number; active_assets: number; hosted_devices: number; open_requests: number };
  supplier_status: string;
  services: { payment: boolean; kyc: boolean };
};

export function AccountDashboard() {
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
    ["进行中订单", summary.metrics.active_orders, Receipt],
    ["有效服务器租约", summary.metrics.active_assets, HardDrives],
  ] as const;
  return (
    <section className="workspace-page">
      <div className="workspace-page__head"><p>PERSONAL OVERVIEW</p><h1>{summary.user.display_name}，欢迎回来</h1><span>{summary.user.email}{summary.user.email_verified ? " · 邮箱已验证" : " · 邮箱待验证"}</span></div>
      <div className="metric-strip">{metrics.map(([label, value, Icon]) => <div key={label}><Icon size={19} /><span>{label}</span><strong>{value}</strong></div>)}</div>
      <section className="workspace-action-list">
        <h2>接下来</h2>
        <Link href="/account/ssh-keys"><span><strong>添加自己的 SSH 公钥</strong><small>平台只接收公钥，私钥始终留在你的设备</small></span><Key size={18} /></Link>
        <Link href="/market"><span><strong>浏览可租用服务器</strong><small>购买后由 Agent 自动授权 SSH 访问</small></span><ArrowRight size={18} /></Link>
        <Link href="/account/leases"><span><strong>查看我的服务器</strong><small>连接命令、到期时间和续费入口集中在这里</small></span><ArrowRight size={18} /></Link>
        {summary.user.role === "supplier"
          ? <Link href="/supplier"><span><strong>返回商家后台</strong><small>报价、资源和交付统一在商家后台处理</small></span><ArrowRight size={18} /></Link>
          : <Link href="/supplier/apply"><span><strong>申请成为商家</strong><small>当前状态：{summary.supplier_status}</small></span><ArrowRight size={18} /></Link>}
      </section>
      {!summary.services.payment && <div className="workspace-service-note">真实支付尚未接入；当前订单使用明确标记的本机占位记账，SSH 租约接口保持不变。</div>}
    </section>
  );
}
