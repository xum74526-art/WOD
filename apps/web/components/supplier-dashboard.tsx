"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Cube, Gear, Receipt, Wallet } from "@phosphor-icons/react";
import { getMobileSupplierDashboard, type MobileSupplierDashboard } from "@/lib/supplier-api";
import { useI18n } from "@/components/locale-root";

const operations = [
  { eyebrow: "LISTING", title: "管理算力商品", description: "维护 GPU、区域、价格、库存与上下架状态。", href: "/supplier/resources", icon: Cube },
  { eyebrow: "DELIVERY", title: "处理交付订单", description: "查看已付款订单，填写有效 SSH 连接信息等待买家确认。", href: "/supplier/orders", icon: Receipt },
  { eyebrow: "REVENUE", title: "查看商家收益", description: "查看订单收益、余额和提现能力。", href: "/supplier/revenue", icon: Wallet },
  { eyebrow: "PROFILE", title: "维护商家资料", description: "更新服务名称、联系人、服务地区和业务说明。", href: "/supplier/settings", icon: Gear },
] as const;

export function SupplierDashboard() {
  const { displayCurrency, formatLedgerMoney } = useI18n();
  const [data, setData] = useState<MobileSupplierDashboard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getMobileSupplierDashboard().then(setData).catch((reason) => setError(reason instanceof Error ? reason.message : "商家数据读取失败"));
  }, []);

  return <section className="workspace-page supplier-overview">
    <div className="workspace-page__head"><p>KAI星算 SUPPLIER / OPERATIONS</p><h1>{data?.company_name || "共享商家后台"}</h1><span>商品、库存、订单、交付和收益全部来自统一KAI星算 API。</span></div>
    {error && <div className="commerce-error">{error}</div>}
    {data && <div className="metric-strip"><div><Cube size={19}/><span>在售商品</span><strong>{data.product_count}</strong></div><div><Receipt size={19}/><span>待交付</span><strong>{data.pending_orders}</strong></div><div><Wallet size={19}/><span>今日收益</span><strong>{formatLedgerMoney(data.today_revenue)}</strong><small>{displayCurrency}</small></div><div><Wallet size={19}/><span>累计收益</span><strong>{formatLedgerMoney(data.total_revenue)}</strong><small>{displayCurrency}</small></div></div>}
    <div className="supplier-operation-line"><span>工作顺序</span><strong>登记商品</strong><i>→</i><strong>买家下单</strong><i>→</i><strong>商家交付 SSH</strong><i>→</i><strong>买家确认</strong></div>
    <div className="role-overview-grid">{operations.map(({ eyebrow, title, description, href, icon: Icon }) => <Link href={href} key={href}><header><Icon size={22}/><small>{eyebrow}</small></header><h2>{title}</h2><p>{description}</p><footer>进入处理 <ArrowRight size={16}/></footer></Link>)}</div>
    <div className="workspace-service-note">Web 不运行独立商家数据库；所有修改都写回统一KAI星算 API。</div>
  </section>;
}
