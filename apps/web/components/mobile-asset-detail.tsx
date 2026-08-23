"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, CalendarDots, Coins, Cpu, Gauge, TrendUp } from "@phosphor-icons/react";
import { getMobileAsset, type MobileAsset } from "@/lib/mobile-business-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

const amount = (value: unknown) => Number(value || 0).toFixed(2);

export function MobileAssetDetail({ id }: { id: number }) {
  const [item, setItem] = useState<MobileAsset | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { getMobileAsset(id).then(setItem).catch((reason) => setError(errorMessage(reason))); }, [id]);
  return <section className="workspace-page mobile-asset-detail"><div className="workspace-page__head"><Link href="/account/assets"><ArrowLeft size={16}/>返回个人资产</Link><p>ACCOUNT / ASSET #{id}</p><h1>{item?.product_name || item?.gpu_model || "资产详情"}</h1><span>查看资产价值、收益、状态和到期信息。</span></div>{error && <div className="commerce-error">{error}</div>}{!item && !error ? <div className="workspace-skeleton"/> : item && <><div className="mobile-data-spine"><article><small>资产价值</small><strong>{amount(item.value)}</strong><span>卡时</span></article><article><small>今日收益</small><strong>{amount(item.today_revenue)}</strong><span>卡时</span></article><article><small>累计收益</small><strong>{amount(item.accumulated_revenue)}</strong><span>卡时</span></article><article><small>剩余时间</small><strong>{item.remaining_days ?? "—"}</strong><span>天</span></article></div><section className="mobile-record-panel asset-detail-facts"><header><Cpu size={20}/><div><small>ASSET FACTS</small><h2>资产信息</h2></div><b>{item.status}</b></header><dl><div><dt>GPU 型号</dt><dd>{item.gpu_model || "—"}</dd></div><div><dt>设备数量</dt><dd>{item.quantity || 1} 台</dd></div><div><dt>购买模式</dt><dd>{item.purchase_type || "—"}</dd></div><div><dt>日收益率</dt><dd>{amount(item.daily_rate)}%</dd></div><div><dt><CalendarDots/>生效时间</dt><dd>{formatDate(item.start_at)}</dd></div><div><dt><CalendarDots/>到期时间</dt><dd>{formatDate(item.end_at)}</dd></div><div><dt><Coins/>当前估值</dt><dd>{item.current_price == null ? "暂不可用" : amount(item.current_price)}</dd></div><div><dt><TrendUp/>持有盈亏</dt><dd>{item.pnl == null ? "暂不可用" : `${item.pnl >= 0 ? "+" : ""}${amount(item.pnl)}`}</dd></div></dl>{item.trading_unavailable_reason && <div className="workspace-service-note"><Gauge size={17}/>{item.trading_unavailable_reason}</div>}</section></>}</section>;
}
