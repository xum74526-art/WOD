"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowClockwise, CalendarDots, Coins, Cpu, Gauge, ShoppingCart, TrendUp } from "@phosphor-icons/react";
import { getMobileAssets, sellMobileAsset, type MobileAssetSummary } from "@/lib/mobile-business-api";
import { errorMessage } from "@/lib/commerce-ui";
import { requestCreateHref } from "@/lib/request-navigation";
import { usePlatformCapabilities } from "@/lib/use-platform-capabilities";
import { assetStatusLabel } from "@/lib/asset-status";
import { useI18n } from "@/components/locale-root";
import { formatFinancialAmount } from "@/lib/financial-format";

const filters = [
  ["all", "asset.filter.all", "全部"],
  ["active", "asset.filter.active", "运行中"],
  ["expired", "asset.filter.expired", "已到期"],
  ["sold", "asset.filter.sold", "已出售"],
] as const;

function amount(value: unknown) {
  return formatFinancialAmount(value as number | string | null | undefined);
}

export function MobileAssetsWorkspace() {
  const { t } = useI18n();
  const { capabilities } = usePlatformCapabilities();
  const directTradeEnabled = capabilities.direct_trade_enabled === true;
  const [data, setData] = useState<MobileAssetSummary | null>(null);
  const [filter, setFilter] = useState<(typeof filters)[number][0]>("all");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(0);

  const load = useCallback(async () => {
    setError("");
    try { setData(await getMobileAssets(filter)); }
    catch (reason) { setError(errorMessage(reason)); }
  }, [filter]);

  useEffect(() => { void load(); }, [load]);

  const metrics = useMemo(() => {
    const items = data?.items ?? [];
    return {
      active: items.filter((item) => item.status === "active").reduce((sum, item) => sum + Math.max(item.quantity || 1, 1), 0),
      expiring: items.filter((item) => item.status === "active" && Number(item.remaining_days) <= 7).length,
      today: items.reduce((sum, item) => sum + Number(item.today_revenue || 0), 0),
    };
  }, [data]);

  async function sell(item: NonNullable<MobileAssetSummary["items"]>[number]) {
    if (!directTradeEnabled || !item.current_unit_price) return;
    if (!window.confirm(`确认按最新有效行情出售？\n预计到账 ${amount(item.current_price)} 卡时\n持有盈亏 ${Number(item.pnl || 0) >= 0 ? "+" : ""}${amount(item.pnl)} 卡时`)) return;
    const id = item.id;
    setBusy(id); setError("");
    try { await sellMobileAsset(id, item.current_unit_price, `web-asset-sale-${crypto.randomUUID()}`.slice(0, 64)); await load(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(0); }
  }

  return <section className="workspace-page mobile-assets-workspace">
    <div className="mobile-ops-head">
      <div><p>ACCOUNT / ASSETS</p><h1>个人资产</h1><span>查看已购算力、运行状态、收益和到期时间。</span></div>
      <Link href={directTradeEnabled ? "/market" : "/account/requests?create=1"}><ShoppingCart size={17}/>{directTradeEnabled ? "购买算力" : "提交需求"}</Link>
    </div>

    <div className="mobile-data-spine" aria-label="资产摘要">
      <article><small>资产总值</small><strong>{amount(data?.total_value)}</strong><span>卡时</span></article>
      <article><small>运行中算力</small><strong>{metrics.active}</strong><span>个实例</span></article>
      <article><small>今日收益</small><strong>{amount(metrics.today)}</strong><span>卡时</span></article>
      <article className={metrics.expiring ? "is-warning" : ""}><small>7 天内到期</small><strong>{metrics.expiring}</strong><span>待续费</span></article>
    </div>

    <div className="mobile-ops-toolbar">
      <nav aria-label="资产状态筛选">{filters.map(([value, key, label]) => <button className={filter === value ? "active" : ""} onClick={() => setFilter(value)} key={value}>{t(key, label)}</button>)}</nav>
      <button onClick={() => void load()}><ArrowClockwise size={16}/>刷新</button>
    </div>

    {error && <div className="commerce-error">{error}</div>}
    {!data ? <div className="workspace-skeleton" aria-label="正在读取个人资产" /> : data.items.length === 0 ? <div className="mobile-empty-state"><Cpu size={31}/><strong>当前分类没有资产</strong><span>已确认的历史资产、设备状态和收益会显示在这里。</span><Link href="/market">进入算力市场</Link></div> : <div className="mobile-asset-ledger">
      <header><span>算力资源</span><span>价值与收益</span><span>运行周期</span><span>状态</span></header>
      {data.items.map((item) => <article key={item.id}>
        <div className="mobile-asset-name"><i className={item.status === "active" ? "running" : ""}/><span><small>ASSET #{item.id}</small><Link href={`/account/assets/${item.id}`}><strong>{item.product_name || item.gpu_model || `算力资产 ${item.id}`}</strong></Link><em>{item.gpu_model || "GPU 算力"} · {item.quantity || 1} 台</em></span></div>
        <div className="mobile-asset-values"><span><Coins size={15}/>当前价值 <b>{amount(item.current_price ?? item.value)}</b></span><span><TrendUp size={15}/>累计收益 <b>{amount(item.accumulated_revenue)}</b></span>{item.pnl != null && <small className={item.pnl >= 0 ? "positive" : "negative"}>盈亏 {item.pnl >= 0 ? "+" : ""}{amount(item.pnl)}</small>}</div>
        <div className="mobile-asset-period"><span><CalendarDots size={15}/>{item.purchase_type === "holding" ? "持有资产" : item.remaining_days == null ? "未提供到期日" : `剩余 ${item.remaining_days} 天`}</span><small>{item.purchase_type === "holding" ? "按有效行情估值" : item.end_at ? new Date(item.end_at).toLocaleDateString("zh-CN") : "—"}</small></div>
        <div className="mobile-asset-status"><b className={`status-${item.status}`}><Gauge size={14}/>{assetStatusLabel(item.status, item.purchase_type, t)}</b>{item.can_sell && (directTradeEnabled ? <button disabled={busy === item.id} onClick={() => void sell(item)}>{busy === item.id ? "处理中" : "出售"}</button> : <Link href={requestCreateHref({ product_id: item.product_id, source: "existing_asset", product_name: item.product_name, gpu_model: item.gpu_model || item.product_name || "GPU", quantity: Math.max(Number(item.quantity) || 1, 1), gpu_hours: 24 })}>提交需求</Link>)}</div>
      </article>)}
    </div>}

    {data && data.audited_earnings_enabled === false && <div className="workspace-service-note">可核验收益数据暂时无法读取；资产价值与状态不受影响。</div>}
  </section>;
}
